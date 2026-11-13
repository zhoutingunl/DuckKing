"""Pinned CPU policies exercised against actual MuJoCo contacts and camera pixels.

CI installs the optional assets. A minimal checkout may skip this module, but
cannot use that skip as evidence that a policy passes physical acceptance.
"""

import asyncio
import gc
import os
import sys
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "external"
pytestmark = pytest.mark.skipif(
    not (ASSETS / "features/policies/hop/policy.onnx").is_file(),
    reason="optional functional-scene assets are not installed",
)


@pytest.fixture
def runtime(monkeypatch):
    environment = {
        key: os.environ.get(key)
        for key in ("MICRODUCK_RL_DIR", "MICRODUCK_POLICY_DIR", "MICRODUCK_ROOT")
    }
    monkeypatch.syspath_prepend(str(ASSETS / "features/python"))
    monkeypatch.syspath_prepend(str(ASSETS / "features/bam"))
    if sys.platform.startswith("linux"):
        monkeypatch.setenv("MUJOCO_GL", "osmesa")
    original_sleep = asyncio.sleep

    async def fast_sleep(delay):
        # Remove only presentation pacing: every MuJoCo step and contact sample
        # is retained, with a scheduler yield for cancellation/worker callbacks.
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    try:
        yield original_sleep
    finally:
        for key, value in environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Native mesh/renderer allocations are much larger than the Python
        # objects that own them, so Python's allocation counter is a poor trigger.
        gc.collect()


@pytest.mark.parametrize(
    ("capability", "actions"),
    [
        (
            "emotions",
            (
                "curious",
                "devastated",
                "yes",
                "sad",
                "mmh",
                "yes_fast",
                "no",
                "defiant",
                "angry",
                "mock",
                "excited",
                "impatient",
                "laugh",
            ),
        ),
        ("dock", ("dock", "undock")),
        ("hop", ("hop",)),
        ("flamingo", ("lift_left", "lift_right", "lower")),
        ("step", ("cross",)),
        ("senses", ("observe", "look_left", "look_forward", "look_right")),
        ("theremin", ("near", "play", "far")),
        ("search", ("find_red", "find_blue", "find_green")),
        ("soccer", ("kick_left", "kick_right")),
        ("navigation", ("go_door", "go_home", "go_table")),
        ("footsteps", ("steps",)),
        ("swing", ("swing",)),
        ("running", ("run",)),
        ("basketball", ("balance_ball", "roll_forward")),
        ("long_jump", ("jump_gap",)),
    ],
)
async def test_pinned_policy_physical_acceptance(runtime, capability, actions):
    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    try:
        assert len(world.geometry()["geoms"]) > 60
        for index, action in enumerate(actions):
            if index and capability not in {"dock", "emotions", "theremin", "senses"}:
                await world.reset()
            world.metrics = {}  # Same command boundary as the real worker.
            if capability in {"running", "basketball", "long_jump"}:
                await world.stop()  # Worker cancels/clears commands before start.
            outcome = await world.perform(FeatureCommand(action=action))
            state = await world.snapshot()
            assert np.isfinite(world.data.qpos).all()
            assert state["geoms"] and state["ducks"]
            if capability == "swing":
                assert outcome["swing_span_deg"] > 20
                assert outcome["verified"] == outcome["geometry_valid"]
                assert len(state["geoms"]) == len(world.geometry()["geoms"])
            else:
                assert outcome["verified"], (capability, action, outcome)
            if capability in {"search", "soccer", "senses", "theremin"}:
                assert state["sensors"]["image"]  # actual rendered RGB, not a mock
            if capability == "dock":
                assert outcome["virtual_battery_percent"] == pytest.approx(22)
                assert outcome["charging_proxy"] == (action == "dock")
            if capability == "running":
                assert outcome["sim_time"] == pytest.approx(5)
                assert outcome["mean_speed_m_s"] > 1
                assert outcome["distance_m"] > 4
                assert state["camera_follow"] == state["ducks"][0]["position"]
            if capability == "basketball":
                assert outcome["sim_time"] == pytest.approx(10)
                assert outcome["supported_seconds"] >= 9
            if capability == "long_jump":
                assert outcome["flight_seconds"] >= 0.1
                assert outcome["target_support_feet"] == 2
                assert outcome["stable_seconds"] >= 1
            await world.stop()
    finally:
        await world.close()


async def test_circus_cancel_releases_thread_and_reset_does_not_start(runtime):
    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "circus")
    try:
        state = await world.snapshot()
        assert len(state["ducks"]) == 3
        assert not world.begin.is_set()
        task = asyncio.create_task(world.perform(FeatureCommand(action="jump_rope")))
        async with asyncio.timeout(60):
            while world.metrics.get("sim_time", 0) <= 2:
                await runtime(0.05)
        assert world.metrics["sim_time"] > 2
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await world.stop()
        assert not world.thread.is_alive()
        await world.reset()
        assert not world.begin.is_set()
        assert (await world.snapshot())["sim_time"] < 2
    finally:
        await world.close()


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        ("hop", "hop"),
        ("movement", "walk"),
        ("basketball", "balance_ball"),
        ("acrobatics", "routine"),
        ("red_light", "play_game"),
    ],
)
async def test_real_worker_cancel_reset_and_release_are_acknowledged(capability, action):
    from duckking.feature_backend import FeatureBackend

    backend = await FeatureBackend.create(ASSETS, capability)
    try:
        assert backend.geometry()["physics"]
        assert (await backend.snapshot())["feature"]["status"] == "idle"
        initial_time = (await backend.snapshot())["sim_time"]
        await asyncio.sleep(0.6)
        assert (await backend.snapshot())["sim_time"] == initial_time
        first = await backend.invoke({"action": action, "request_id": "physical-action"})
        assert first["status"] == "running"
        assert (await backend.snapshot())["feature"]["status"] == "running"
        await asyncio.sleep(0.2)
        await backend.stop()
        stopped_time = (await backend.snapshot())["sim_time"]
        await asyncio.sleep(0.6)
        assert (await backend.snapshot())["sim_time"] == stopped_time
        await backend.reset()
        for _ in range(100):
            if (await backend.snapshot())["feature"]["status"] == "idle":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("reset did not publish idle state")
        assert not backend.error
    finally:
        await backend.close()
    assert backend.process.returncode is not None
    with pytest.raises(ValueError, match="释放"):
        await backend.invoke({"action": action})


async def test_ball_policy_is_blind_and_memory_resets(runtime):
    import mujoco
    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "basketball")
    try:
        observation = world.observations()
        ball = world.model.joint("ball_root").qposadr[0]
        world.data.qpos[ball] += 0.1
        mujoco.mj_forward(world.model, world.data)
        np.testing.assert_array_equal(world.observations(), observation)
        assert not observation[51:61].any()
        await world.reset()
        world.tick()
        assert any(v.any() for v in world.memory.values())
        await world.stop()
        stopped = world.data.time
        await world.snapshot()
        assert world.data.time == stopped
        outcome = await world.perform(FeatureCommand(action="balance_ball"))
        assert outcome["verified"] and world.data.time > stopped + 9.9
        assert any(v.any() for v in world.memory.values())
        await world.reset()
        assert not any(v.any() for v in world.memory.values())
        assert world.data.time == 0
    finally:
        await world.close()


async def test_ball_worker_continues_then_recovers_only_after_leaving_ball(runtime):
    import io

    import mujoco
    import numpy as np

    from duckking.feature_worker import Worker
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "basketball")
    resets = []
    original_reset = world.reset

    async def reset():
        await original_reset()
        resets.append((float(world.data.time), all(not v.any() for v in world.memory.values())))

    world.reset = reset
    worker = Worker(world, "basketball", "physics-continuation", io.StringIO())
    try:
        await worker.handle({"id": "first", "command": {
            "action": "balance_ball", "request_id": "first"}})
        await worker.task
        assert worker.current["verified"] and world.data.time == pytest.approx(10)
        pose, velocity = world.data.qpos.copy(), world.data.qvel.copy()
        memory = {k: v.copy() for k, v in world.memory.items()}
        ball = world.model.body("ball").id
        ball_start = world.data.xpos[ball, :2].copy()
        await worker.handle({"id": "second", "command": {
            "action": "roll_forward", "request_id": "second"}})
        assert worker.current["preparation"] == "continue" and not resets
        np.testing.assert_array_equal(world.data.qpos, pose)
        np.testing.assert_array_equal(world.data.qvel, velocity)
        for key in memory:
            np.testing.assert_array_equal(world.memory[key], memory[key])
        await worker.task
        assert worker.current["verified"] and world.data.time == pytest.approx(20)
        distance = float(np.linalg.norm(world.data.xpos[ball, :2] - ball_start))
        assert worker.current["outcome"]["ball_travel_m"] == pytest.approx(distance)
        assert not resets

        # A physical disturbance moves the free base off the ball. This is
        # test setup, not an action outcome or a successful recovery policy.
        world.data.qpos[2] = 0.06
        mujoco.mj_forward(world.model, world.data)
        await worker.handle({"id": "third", "command": {
            "action": "balance_ball", "request_id": "third"}})
        assert worker.current["phase"] == "preparing"
        await worker.task
        assert resets == [(0, True)]
        assert worker.current["restarted"] and worker.current["verified"]
        assert world.data.time == pytest.approx(10)
        assert [r["id"] for r in worker.results] == ["first", "second", "third"]
    finally:
        await worker.cancel()
        await world.close()


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        ("running", "run"),
        ("basketball", "balance_ball"),
        ("long_jump", "jump_gap"),
    ],
)
async def test_playground_physical_failure_is_not_success(runtime, capability, action):
    import mujoco

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    try:
        if capability == "running":
            world.data.qpos[3:7] = [0.70710678, 0.70710678, 0, 0]
        else:
            world.data.qpos[:3] = [0.15, 0, 0.125]  # on the floor, not the ball/platform
        mujoco.mj_forward(world.model, world.data)
        result = await world.perform(FeatureCommand(action=action))
        assert result["verified"] is False
        assert world.data.time < 1
    finally:
        await world.close()


async def test_playground_rejects_invalid_network_output_before_physics(runtime, monkeypatch):
    from types import SimpleNamespace

    import numpy as np

    from duckking.feature_worlds import make_world

    for capability in ("basketball", "long_jump"):
        world = make_world(ASSETS, capability)
        try:
            outputs = (
                [np.zeros((1, 14), np.float32), np.full((1, 1, 256), np.nan), np.zeros((1, 1, 256))]
                if capability == "basketball"
                else [np.full((1, 14), 100)]
            )
            monkeypatch.setattr(
                world,
                "policy",
                SimpleNamespace(
                    get_inputs=world.policy.get_inputs,
                    run=lambda *args, values=outputs: values,
                ),
            )
            with pytest.raises(ValueError, match="策略输出"):
                world.tick()
            assert world.data.time == 0
        finally:
            await world.close()


@pytest.mark.parametrize("height", [10, 15, 20, 25, 50, 100, 140, 200])
async def test_stilt_heights_use_matched_morphology_and_bounded_trial(runtime, height):
    import json

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "stilts", variant=height)
    try:
        initial = await world.snapshot()
        assert initial["stilt_height_m"] == pytest.approx(height / 100)
        assert world.data.qpos[2] == pytest.approx(0.125 + height / 100)
        assert len(world.geometry()["geoms"]) > 10
        outcome = await world.perform(FeatureCommand(action="stilt_walk"))
        # Cross-platform contact trajectories can diverge (20 cm failed the
        # Linux rollout). Test truthful acceptance and bounded/frozen physics,
        # rather than changing physics to guarantee a selected rollout wins.
        assert 0 < world.data.time <= 10.001
        assert outcome["distance_m"] == pytest.approx(
            float((world.data.qpos[:2] ** 2).sum() ** 0.5)
        )
        assert outcome["verified"] is (
            world.data.time >= 9.99 and world.upright() >= 0.65 and outcome["distance_m"] > 0.3
        )
        if world.data.time < 9.99:
            assert world.upright() < 0.65
        elif not outcome["verified"]:
            assert outcome["distance_m"] <= 0.3
        paused = world.data.time
        await world.snapshot()
        assert world.data.time == paused
        json.dumps(outcome)  # No NumPy bool/scalar may break the worker framing.
        with pytest.raises(ValueError, match="重置"):
            await world.perform(FeatureCommand(action="stilt_walk"))
        await world.reset()
        assert world.data.time == 0
    finally:
        await world.stop()


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        ("standup", "recover_back"),
        ("standup", "recover_front"),
        ("terrain_slip", "try_course"),
        ("terrain_rough", "try_course"),
        ("terrain_slope", "try_course"),
        ("terrain_stairs", "try_course"),
        ("terrain_gale", "try_course"),
        ("giant_ball", "try_course"),
        ("runup_roll", "try_trick"),
        ("roller_slalom", "try_trick"),
    ],
)
async def test_expansion_real_physical_completion_and_explicit_reset(runtime, capability, action):
    import json

    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    try:
        result = await world.perform(FeatureCommand(action=action))
        assert result["verified"] is True
        assert np.isfinite(world.data.qpos).all()
        json.dumps(result)
        if capability == "roller_slalom":
            assert result["gates_passed"] == 8 and result["cones_hit"] == 0
        if capability == "giant_ball":
            assert result["foot_ball_contacts"] > 0 and result["ball_travel_m"] > 0.1
        with pytest.raises(ValueError, match="重置"):
            await world.perform(FeatureCommand(action=action))
        t = world.data.time
        await world.snapshot()
        assert world.data.time == t
        await world.reset()
        assert not world.metrics
    finally:
        await world.stop()


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        ("climb", "try_climb"),
        ("backflip", "flip"),
        ("roller_glide", "try_trick"),
    ],
)
async def test_unfinished_expansion_experiments_never_claim_success(runtime, capability, action):
    import json

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    result = await world.perform(FeatureCommand(action=action))
    assert result["verified"] is False and result["message"]
    json.dumps(result)
    await world.stop()
    t = world.data.time
    await world.snapshot()
    assert world.data.time == t
    await world.reset()
    assert world.data.time == pytest.approx(1.2 if capability == "roller_glide" else 0)


async def test_gust_cancel_clears_force_and_freezes_physics(runtime):
    import io

    import numpy as np

    from duckking.feature_worker import Worker
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "terrain_gale")
    worker = Worker(world, "terrain_gale", "test", io.StringIO())
    await worker.handle({"id": "start", "command": {"action": "try_course"}})
    for _ in range(10):
        await runtime(0)
    await worker.cancel()
    assert not np.any(world.data.xfrc_applied)
    assert not np.any(world.command)
    t = world.data.time
    await runtime(0.02)
    assert world.data.time == t


async def test_tof_grid_has_real_occlusion_ranges_and_does_not_advance_on_read(runtime):
    import numpy as np

    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "tof")
    try:
        frame = await world.snapshot()
        grid = frame["sensors"]["depth_grid_m"]
        assert len(grid) == 8 and all(len(row) == 8 for row in grid)
        values = [x for row in grid for x in row if x is not None]
        assert values and all(np.isfinite(v) and 0 <= v <= 4 for v in values)
        assert frame["sensors"]["scan_fov_deg"] == 45
        now = world.data.time
        assert (await world.snapshot())["sensors"]["depth_grid_m"] == grid
        assert world.data.time == now
    finally:
        await world.close()


@pytest.mark.parametrize(
    "capability", ["sprint_race", "roller_race", "hill_race", "red_light", "tug"]
)
async def test_bounded_games_use_actual_finish_or_rope_and_freeze(runtime, capability):
    import json

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    result = await world.perform(FeatureCommand(action="play_game"))
    assert result["verified"] is True
    if capability == "tug":
        assert result["winner"] in {"a", "b", "draw"}
        assert result["rope_gap_m"] < 0.05
        assert result["elapsed_seconds"] <= 45.01
    else:
        assert result["distance_m"] >= world.length
        if capability == "red_light":
            assert result["red_lights"] >= 1
    json.dumps(await world.snapshot())
    await world.stop()
    t = world.data.time
    await world.snapshot()
    assert world.data.time == t
    with pytest.raises(ValueError, match="重置"):
        await world.perform(FeatureCommand(action="play_game"))
    await world.reset()
    assert world.trial_started is False and not world.metrics


async def test_tug_rejects_detached_rope_before_awarding_winner(runtime):
    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "tug")
    world.data.eq_active[world.model.equality("rope_connection").id] = False
    result = await world.perform(FeatureCommand(action="play_game"))
    assert result["verified"] is False
    assert "连接异常" in result["message"]
    await world.stop()


@pytest.mark.parametrize("action", ["routine", "backroll", "headstand", "spin_left", "spin_right"])
async def test_acrobatics_judges_every_transition_and_resets_delay_history(runtime, action):
    import json

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "acrobatics")
    result = await world.perform(FeatureCommand(action=action))
    assert result["verified"] is True and result["stages_completed"] >= 3
    assert world.sim.state()["upright"] >= 0.9
    json.dumps(await world.snapshot())
    await world.stop()
    t = world.data.time
    await world.snapshot()
    assert world.data.time == t
    await world.reset()
    assert world.data.time == 0 and world.sim._pending == []


async def test_acrobatics_invalid_output_rejected_before_any_physics_step(runtime):
    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, "acrobatics")
    world.policies["walk"].policy = lambda obs: np.full(14, np.nan, dtype=np.float32)
    before = world.data.time
    with pytest.raises(ValueError, match="策略输出无效"):
        await world.perform(FeatureCommand(action="routine"))
    assert world.data.time == before
    await world.close()


@pytest.mark.parametrize(
    ("capability", "action"),
    [
        ("terrain_step", "try_course"),
        ("chimney", "try_climb"),
    ],
)
async def test_platform_sensitive_trials_report_actual_contacts_and_bounded_failure(
    runtime, capability, action
):
    import json

    import numpy as np

    from duckking.feature_catalog import FeatureCommand
    from duckking.feature_worlds import make_world

    world = make_world(ASSETS, capability)
    try:
        initial_time = world.data.time
        result = await world.perform(FeatureCommand(action=action))
        elapsed = world.data.time - initial_time
        assert np.isfinite(world.data.qpos).all()
        if capability == "terrain_step":
            # Same 25 mm physical descent and strict success gate on every OS.
            assert 0 < elapsed <= 10.001
            expected = bool(
                elapsed >= 9.99
                and world.upright() >= 0.5
                and world.data.qpos[0] > 0.4
                and world.data.qpos[2] < 0.15
            )
            if elapsed < 9.99:
                assert world.upright() < 0.5
        else:
            assert 0 < elapsed <= 60.001
            assert result["climb_height_m"] >= world.data.qpos[2]
            expected = bool(
                result["phase"] == 3
                and result["stable_seconds"] >= 2
                and all(world.feet_on("course_platform"))
                and world.upright() > 0.85
                and np.linalg.norm(world.data.qvel[:3]) < 0.08
            )
            if not expected and elapsed < 59.99:
                assert elapsed > 2 and world.data.qpos[2] < 0.065
        assert result["verified"] is expected, result
        assert result["message"]
        json.dumps(result)
        with pytest.raises(ValueError, match="重置"):
            await world.perform(FeatureCommand(action=action))
        await world.stop()
        t = world.data.time
        await world.snapshot()
        assert world.data.time == t
        await world.reset()
        assert world.data.time == pytest.approx(initial_time) and not world.metrics
    finally:
        await world.close()

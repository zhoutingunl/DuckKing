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
        with pytest.raises(ValueError, match="重置"):
            await world.perform(FeatureCommand(action="balance_ball"))
        await world.reset()
        assert not any(v.any() for v in world.memory.values())
        assert world.data.time == 0
    finally:
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

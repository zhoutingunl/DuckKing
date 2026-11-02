"""Real passive dynamics, command ownership, policy integrity, and voice routing."""

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import mujoco
import numpy as np
import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.config import Settings
from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController
from duckking.rooms import RoomRegistry
from duckking.seesaw import CONTRACT, DURATION, OBSERVATION_SIZE, WEIGHT_MASS, SeesawWorld
from duckking.seesaw_backend import SeesawArtifacts, SeesawBackend
from duckking.seesaw_policy import SeesawPolicy
from duckking.voice import VoiceSession

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture(scope="module")
def compiled():
    return SeesawWorld(ASSETS)


@pytest.fixture
def world(compiled):
    return SeesawWorld(
        ASSETS, compiled=(compiled.model, compiled.fingerprint), session=compiled.session
    )


@pytest.fixture
def backend(tmp_path, monkeypatch, compiled):
    def factory(assets, *, compiled_model=None, session=None, **kwargs):
        return SeesawWorld(
            assets,
            compiled=kwargs.get("compiled") or (compiled.model, compiled.fingerprint),
            session=session or compiled.session,
        )

    monkeypatch.setattr("duckking.seesaw_backend.SeesawWorld", factory)
    return SeesawBackend(ASSETS, SeesawArtifacts(tmp_path))


def rollout(world, action, steps=int(DURATION / 0.1)):
    for _ in range(steps):
        _, _, done, _, info = world.step(action(world.observation()))
        if done:
            break
    return info


def test_passive_board_has_no_actuator_and_contact_drives_its_angle(world):
    m, d = world.model, world.data
    hinge = m.joint("seesaw_hinge").id
    assert m.nu == 14 and hinge not in m.actuator_trnid[:, 0]
    assert m.jnt_stiffness[hinge] == 0 and m.dof_damping[world.hinge_v] == 10
    world.reset(0)
    rollout(world, lambda _: 0, 8)
    positive = world.measure()
    # Positive x presses the green end DOWN; contact torque is positive around +Y.
    assert positive["angle_deg"] > 1 and positive["contact_torque_nm"] > 0
    assert d.qfrc_actuator[world.hinge_v] == 0
    assert d.qfrc_applied.sum() == 0 and not d.xfrc_applied.any()
    # Away from limits, the hinge generalized contact force equals the measured
    # contact moment. This catches reversing geom1/geom2 in the UI telemetry.
    assert positive["contact_torque_nm"] == pytest.approx(
        d.qfrc_constraint[world.hinge_v], abs=0.02
    )


def test_same_start_different_actions_change_environment_without_scripted_tilt(world):
    world.reset(0)
    held = rollout(world, lambda _: 0, 70)
    world.reset(0)
    rollout(world, lambda _: 2, 40)
    moved = rollout(world, lambda _: 0, 30)
    assert moved["position_m"] < held["position_m"] - 0.08
    assert moved["angle_deg"] < held["angle_deg"] - 3
    assert moved["contacts"] > 0
    assert abs(moved["weight_position_m"] - held["weight_position_m"]) > 0.03


def test_reset_reproduces_contacts_board_response_and_gait_history(world):
    trajectories = []
    for _ in range(2):
        world.reset(17)
        trajectory = []
        for _ in range(20):
            world.step(0)
            trajectory.append(world.data.qpos.copy())
        trajectories.append(trajectory)
    np.testing.assert_allclose(*trajectories, atol=1e-12)
    first = world.start_x
    world.reset(18)
    assert world.start_x != first and world.observation().shape == (OBSERVATION_SIZE,)


def test_level_board_is_not_success_when_weight_is_outside_dock(world):
    world.reset(1)
    # Exercise a known level terminal state, not the platform-dependent final
    # angle of an 18-second closed-loop rollout of the untrained rule.
    world.data.qpos[world.hinge_q] = 0
    world.data.qvel[world.hinge_v] = 0
    world.data.qpos[world.slider_q] = 0.2
    world.data.qvel[world.slider_v] = 0
    world.steps = int(DURATION / 0.1) - 1
    world.hold = 2
    mujoco.mj_forward(world.model, world.data)
    _, _, done, _, controlled = world.step(0)
    assert done and controlled["contacts"] > 0
    assert abs(controlled["angle_deg"]) < 2
    assert abs(controlled["weight_position_m"]) > 0.19
    assert controlled["hold_seconds"] == 0
    assert not controlled["success"] and controlled["reason"] == "not_docked"


def test_massive_slider_and_board_are_passive_without_any_duck_contact(world):
    assert world.model.body_mass[world.weight_body] == pytest.approx(WEIGHT_MASS)
    joint = world.model.joint("seesaw_slider").id
    assert joint not in world.model.actuator_trnid[:, 0]
    assert world.model.jnt_stiffness[joint] == 0
    angles = []
    for direction in (-1, 1):
        world.reset(0)
        # Initial conditions only: duck is away, load starts off center at rest.
        world.data.qpos[world.driver.root] = 2
        world.data.qpos[world.slider_q] = 0.2 * direction
        mujoco.mj_forward(world.model, world.data)
        for _ in range(250):
            mujoco.mj_step(world.model, world.data)
        assert direction * world.data.qpos[world.slider_q] > 0.23
        assert world.data.qfrc_actuator[world.slider_v] == 0
        assert world.data.qfrc_actuator[world.hinge_v] == 0
        assert not world.data.qfrc_applied.any() and not world.data.xfrc_applied.any()
        angles.append(world.data.qpos[world.hinge_q])
    assert angles[0] < -0.03 and angles[1] > 0.03


def test_returning_duck_to_center_does_not_return_free_weight_to_dock(world):
    world.reset(0)
    centered = rollout(world, SeesawWorld.center_action)
    assert not centered["success"] and centered["reason"] == "not_docked"
    assert abs(centered["position_m"]) < 0.04
    assert abs(centered["weight_position_m"]) > 0.3
    assert "center" not in centered["reward_terms"]


@pytest.mark.parametrize("position,velocity", [(0.09, 0), (0, 0.15)])
def test_outside_dock_or_fast_crossing_cannot_receive_terminal_success(world, position, velocity):
    world.reset(0)
    # Construct terminal initial states; no hidden latch or attraction at the dock.
    world.data.qpos[world.driver.root] = -0.005
    world.data.qpos[world.slider_q] = position
    world.data.qvel[world.slider_v] = velocity
    world.steps = int(DURATION / 0.1) - 1
    world.hold = 2
    mujoco.mj_forward(world.model, world.data)
    _, _, done, _, info = world.step(0)
    assert done and not info["success"] and info["reason"] == "not_docked"
    assert info["hold_seconds"] == 0


@pytest.mark.parametrize("action", [True, -1, 3, 0.5, float("nan"), [0]])
def test_invalid_actions_cannot_advance_physics(world, action):
    before = world.data.qpos.copy()
    with pytest.raises(ValueError):
        world.step(action)
    np.testing.assert_array_equal(before, world.data.qpos)


def test_unbounded_walking_terminates_at_real_foot_boundary(world):
    world.reset(0)
    info = rollout(world, lambda _: 1)
    assert world.done and info["reason"] == "fell_or_left_board"
    assert info["seconds"] < DURATION and not info["success"]
    with pytest.raises(RuntimeError):
        world.step(0)


async def test_missing_policy_and_bad_commands_leave_current_run_intact(backend):
    await backend.invoke({"operation": "start", "controller": "baseline", "seed": 2})
    for args in (
        {"operation": "start", "controller": "trained"},
        {"operation": "start", "seed": True},
        {"operation": "nudge", "direction": "forward", "seconds": 999},
        {"operation": "start", "direction": "forward"},
        {"operation": "reset", "seed": -1},
    ):
        with pytest.raises(ValueError):
            await backend.invoke(args)
        assert backend.world.seed == 2 and backend.phase == "running"
    with pytest.raises(ValueError, match="不能叠加"):
        await backend.prepare(Action(name="walk"))
    await backend.close()


async def test_stop_and_reset_are_bounded_and_no_delayed_motion_revives(backend):
    await backend.invoke({"operation": "nudge", "direction": "forward", "seconds": 3})
    room = SimpleNamespace(
        viewers=0,
        voice=None,
        motion=SimpleNamespace(current=None),
        scene_motion=MotionController(backend),
    )
    assert RoomRegistry.busy(room)
    await asyncio.sleep(0.16)
    await asyncio.wait_for(backend.stop(), 1)
    assert backend.phase == "cancelled" and backend.task.done()
    assert not RoomRegistry.busy(room)
    position = backend.world.data.qpos.copy()
    await asyncio.sleep(0.15)
    np.testing.assert_array_equal(position, backend.world.data.qpos)
    await backend.reset()
    assert backend.world.data.time == 0 and backend.baseline.data.time == 0
    await backend.close()
    with pytest.raises(ValueError, match="关闭"):
        await backend.invoke({"operation": "start", "controller": "baseline"})


async def test_pause_freezes_moving_weight_without_zeroing_its_physical_velocity(
    backend, monkeypatch
):
    moved, loop, tick = asyncio.Event(), asyncio.get_running_loop(), backend._tick

    def observe_tick(action):
        tick(action)
        if backend.world.data.time >= 0.6:
            loop.call_soon_threadsafe(moved.set)

    monkeypatch.setattr(backend, "_tick", observe_tick)
    await backend.invoke({"operation": "nudge", "direction": "hold", "seconds": 3})
    await asyncio.wait_for(moved.wait(), 5)
    await backend.stop()
    data, index = backend.world.data, backend.world.slider_v
    assert abs(data.qvel[index]) > 0.01
    before, speed, seconds = data.qpos.copy(), float(data.qvel[index]), float(data.time)
    await asyncio.sleep(0.15)
    np.testing.assert_array_equal(before, data.qpos)
    assert data.time == seconds and data.qvel[index] == speed
    await backend.reset()
    assert data.time == 0 and data.qpos[backend.world.slider_q] == backend.world.load_start
    await backend.close()


async def test_stop_supersedes_start_waiting_on_previous_loop(backend, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def halt():
        entered.set()
        await release.wait()

    monkeypatch.setattr(backend, "_halt", halt)
    start = asyncio.create_task(backend.invoke({"operation": "start", "controller": "baseline"}))
    await entered.wait()
    stop = asyncio.create_task(backend.stop())
    await asyncio.sleep(0)
    release.set()
    await stop
    with pytest.raises(ValueError, match="取消"):
        await start
    assert backend.task is None


async def test_pair_has_same_initial_state_but_independent_passive_response(backend):
    await backend.invoke({"operation": "start", "controller": "baseline", "seed": 0})
    np.testing.assert_array_equal(backend.world.data.qpos, backend.baseline.data.qpos)
    assert backend.world.data is not backend.baseline.data
    assert backend.world.driver.last is not backend.baseline.driver.last
    backend.policy = lambda _: 1
    await asyncio.sleep(0.21)
    state = await backend.snapshot()
    assert state["sim_time"] == state["comparison"]["baseline"]["sim_time"]
    assert not np.array_equal(backend.world.data.qpos, backend.baseline.data.qpos)
    assert state["seesaw"]["trace"] and state["seesaw"]["comparison"]["controller"] == "center"
    await backend.close()


async def test_human_pk_commands_only_left_expire_replace_and_cancel(backend, world, monkeypatch):
    # Park the scheduler to exercise exact physics ticks without wall-clock races.
    release = asyncio.Event()

    async def parked_loop(*_):
        await release.wait()

    monkeypatch.setattr(backend, "_loop", parked_loop)
    await backend.invoke({"operation": "start", "mode": "duel", "controller": "baseline"})
    task = backend.task
    world.reset(0)
    try:
        motion = MotionController(backend)
        mcp = DeviceMCP(motion, "test")
        request = {
            "jsonrpc": "2.0",
            "id": 501,
            "method": "tools/call",
            "params": {
                "name": "duck_seesaw",
                "arguments": {
                    "operation": "nudge",
                    "direction": "backward",
                    "seconds": 1,
                },
            },
        }
        first = await mcp.handle(request)
        assert not first["result"]["isError"]
        for _ in range(5):
            backend._tick(0)
            world.step(0)
        deadline = backend.human_until
        assert await mcp.handle(request) == first
        assert backend.human_until == deadline  # A transport replay cannot extend walking.
        for _ in range(6):
            backend._tick(0)
            world.step(0)
        assert backend.baseline.last_action == 0
        assert backend.summary()["human_command"]["remaining_seconds"] == 0
        np.testing.assert_array_equal(backend.world.data.qpos, world.data.qpos)
        assert backend.baseline.measure()["position_m"] < world.measure()["position_m"] - 0.02
        assert backend.world.data.time == backend.baseline.data.time
        assert backend.task is task and backend.mode == "duel"
        await backend.invoke({"operation": "nudge", "direction": "forward", "seconds": 3})
        backend._tick(0)
        assert backend.baseline.last_action == 1
        await backend.invoke({"operation": "nudge", "direction": "hold"})
        backend._tick(0)
        assert (
            backend.baseline.last_action == 0 and backend.human_until <= backend.baseline.data.time
        )
        before = backend.world.data.time
        with pytest.raises(ValueError):
            await backend.invoke({"operation": "nudge", "direction": "forward", "seconds": 4})
        assert backend.world.data.time == before and backend.task is task
    finally:
        release.set()
        await backend.stop()
    assert backend.human_action == backend.human_until == 0
    with pytest.raises(ValueError, match="结束或暂停"):
        await backend.invoke({"operation": "nudge", "direction": "forward"})
    await backend.reset()
    assert backend.world.data.time == backend.baseline.data.time == 0
    await backend.close()


async def test_compare_cannot_be_replaced_by_accidental_voice_nudge(backend):
    await backend.invoke({"operation": "start", "controller": "baseline"})
    task = backend.task
    with pytest.raises(ValueError, match="规则对照进行中"):
        await backend.invoke({"operation": "nudge", "direction": "forward"})
    assert backend.task is task and backend.phase == "running"
    with pytest.raises(ValueError):
        await backend.invoke({"operation": "start", "mode": "unknown"})
    await backend.close()


def test_red_dock_is_display_only_and_does_not_invalidate_evaluated_policy(backend):
    original = backend.world.model.geom_rgba.copy()
    red = [
        g
        for g in backend.geometry()["geoms"]
        if backend.world.model.geom(g["id"]).name.startswith("seesaw_dock")
    ]
    assert len(red) == 3 and all(g["rgba"] == [0.85, 0.08, 0.10, 1.0] for g in red)
    np.testing.assert_array_equal(original, backend.world.model.geom_rgba)
    policy = SeesawArtifacts(ASSETS.parent / "training/seesaw_results").policy(
        "trained", backend.world.manifest()
    )
    assert policy(backend.world.observation()) in (0, 1, 2)
    assert backend.revision.endswith("-red1")


async def test_bad_inference_pauses_both_worlds_without_fallback(backend):
    await backend.invoke({"operation": "start", "controller": "baseline"})
    backend.policy = lambda _: float("nan")
    await asyncio.wait_for(backend.task, 1)
    assert backend.phase == backend.baseline_phase == "failed"
    assert backend.error and backend.world.data.time == 0
    await backend.close()


async def test_mcp_tools_are_scene_specific_and_replays_do_not_restart(backend):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "test")
    listing = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert {t["name"] for t in listing["result"]["tools"]} == {
        "duck_seesaw",
        "duck_stop",
        "duck_get_status",
    }
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "duck_seesaw",
            "arguments": {"operation": "nudge", "direction": "backward"},
        },
    }
    first = await mcp.handle(request)
    task = backend.task
    assert await mcp.handle(request) == first and backend.task is task
    request["params"]["arguments"]["direction"] = "forward"
    assert "error" in await mcp.handle(request)
    denied = await mcp.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "duck_walk_short"}}
    )
    assert denied["result"]["isError"]
    status = await mcp.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "duck_get_status"}}
    )
    compact = json.loads(status["result"]["content"][0]["text"])
    assert compact["phase"] == "running" and "trace" not in compact and "geoms" not in compact
    assert "geoms" not in compact["comparison"]
    await motion.close()


async def test_new_utterance_preserves_challenge_but_disconnect_stops(backend, tmp_path):
    motion = MotionController(backend)
    session = VoiceSession(AsyncMock(), motion, Settings(data_dir=tmp_path))
    backend.stop = AsyncMock()
    session.pending_input = {"frames": [], "stopped": False}
    await session._stop_motion()
    backend.stop.assert_not_called()
    session.pending_input = None
    await session._stop_motion()
    backend.stop.assert_awaited()
    await motion.close()


def test_policy_contract_shape_and_nonfinite_values_fail_closed(world, tmp_path):
    payload = {**world.manifest(), "steps": 0, "layers": []}
    width = OBSERVATION_SIZE
    for outputs in (64, 64, 3):
        payload["layers"].append(
            {"weight": np.zeros((outputs, width)).tolist(), "bias": np.zeros(outputs).tolist()}
        )
        width = outputs
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload))
    assert SeesawPolicy(path, world.manifest())(world.observation()) == 0
    for key, value in (("contract", "other"), ("model_sha256", "other"), ("steps", True)):
        altered = {**payload, key: value}
        path.write_text(json.dumps(altered))
        with pytest.raises(ValueError):
            SeesawPolicy(path, world.manifest())
    payload["layers"][0]["weight"][0][0] = float("nan")
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        SeesawPolicy(path, world.manifest())
    payload["layers"][0]["weight"] = np.full((64, OBSERVATION_SIZE), 1e38).tolist()
    path.write_text(json.dumps(payload))
    policy = SeesawPolicy(path, world.manifest())
    with pytest.raises(ValueError, match="非有限值"):
        policy(np.full(OBSERVATION_SIZE, 1e38))


def test_api_uses_room_ownership_and_never_exposes_unprepared_state(
    tmp_path, monkeypatch, compiled
):
    monkeypatch.setenv("DUCKKING_SEESAW_ARTIFACTS", str(tmp_path))
    monkeypatch.setattr(
        "duckking.seesaw_backend.SeesawWorld",
        lambda *args, **kwargs: SeesawWorld(
            ASSETS, compiled=(compiled.model, compiled.fingerprint), session=compiled.session
        ),
    )
    app = create_app(settings=Settings(data_dir=tmp_path / "private"))
    with TestClient(app) as client:
        assert client.get("/api/seesaw/training").json() == {"report": None}
        assert client.post("/api/seesaw/command", json={"operation": "start"}).status_code == 409
        assert (
            client.post(
                "/api/seesaw/prepare", json={}, headers={"Origin": "https://attacker.invalid"}
            ).status_code
            == 403
        )
        result = client.post("/api/seesaw/prepare", json={})
        assert result.status_code == 200 and result.json()["backend"]["scene"] == "seesaw"
        assert client.post("/api/seesaw/command", json={"operation": "start"}).status_code == 422
        assert client.post("/api/seesaw/prepare?room=99", json={}).status_code == 404
        assert client.get("/api/seesaw/training").headers["cache-control"] == "no-store"


def test_bundled_policy_and_report_match_actual_contract(world):
    directory = Path(__file__).resolve().parents[1] / "training/seesaw_results"
    artifacts = SeesawArtifacts(directory)
    assert artifacts.report()["manifest"]["contract"] == CONTRACT
    # Historical driven/static scores cannot be attributed to the passive task.
    for old in ("static-v2", "driven-v3"):
        with pytest.raises(ValueError, match="匹配"):
            SeesawArtifacts(directory / old).policy("trained", world.manifest())
    policy = artifacts.policy("trained", world.manifest())
    assert policy.steps == artifacts.report()["selected_steps"]
    # Bind the published experiment to its actual actor/report/environment.
    checksums = json.loads((directory / "checksums.json").read_text())
    assert set(checksums) == {"policy.json", "early.json", "report.json", "environment.json"}
    for name, expected in checksums.items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
    rows = {row["seed"]: row for row in artifacts.report()["test"]["results"]}
    assert sum(row["success"] for row in rows.values()) == 98
    assert {seed for seed, row in rows.items() if not row["success"]} == {30018, 30056}
    # Closed-loop contacts and categorical decisions amplify numerical differences
    # across OS/BLAS/ONNX builds. CI must reproduce its own rollouts, not pretend
    # the archived macOS failures are universal Linux failures.
    for seed in (30000, 30018):
        world.reset(seed)
        info = rollout(world, policy)
        assert info["seconds"] <= DURATION + 1e-6
        if seed == 30000:
            assert info["success"] and info["reason"] == "success"
            assert abs(info["dock_error_m"]) < 0.04 and info["hold_seconds"] >= 1 - 1e-6
        world.reset(seed)
        repeated = rollout(world, policy)
        assert repeated["success"] == info["success"]
        assert repeated["reason"] == info["reason"]
        for key in ("seconds", "weight_position_m", "angle_deg", "hold_seconds"):
            assert repeated[key] == pytest.approx(info[key], abs=1e-10)

"""Real passive dynamics, command ownership, policy integrity, and voice routing."""

import asyncio
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
    assert m.nu == 15 and hinge not in m.actuator_trnid[:, 0]
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
    held = rollout(world, lambda _: 0, 20)
    world.reset(0)
    moved = rollout(world, lambda _: 2, 20)
    assert moved["position_m"] < held["position_m"] - 0.08
    assert moved["angle_deg"] < held["angle_deg"] - 3
    assert moved["contacts"] > 0


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


def test_rule_is_separate_baseline_and_hinge_limit_is_not_success(world):
    world.reset(0)
    held = rollout(world, lambda _: 0)
    assert not held["success"] and held["reason"] == "not_balanced"
    assert held["seconds"] == pytest.approx(DURATION)
    assert abs(held["angle_deg"]) > 5
    world.reset(0)
    controlled = rollout(world, SeesawWorld.rule_action)
    assert abs(controlled["angle_deg"]) < abs(held["angle_deg"]) / 3
    assert controlled["reason"] in {"success", "not_balanced"}


def test_massive_slider_drives_passive_board_without_any_duck_contact(world):
    assert world.model.body_mass[world.weight_body] == pytest.approx(WEIGHT_MASS)
    joint = world.model.joint("seesaw_slider").id
    assert world.model.actuator_trnid[world.slider_drive, 0] == joint
    angles = []
    for direction in (-1, 1):
        world.reset(0)
        # Set initial conditions only; keep the duck away from this load-only test.
        world.data.qpos[world.driver.root] = 2
        world.data.ctrl[world.slider_drive] = 0.2 * direction
        mujoco.mj_forward(world.model, world.data)
        for _ in range(250):
            mujoco.mj_step(world.model, world.data)
        assert abs(world.data.qpos[world.slider_q]) > 0.15
        assert world.data.qfrc_actuator[world.hinge_v] == 0
        assert not world.data.qfrc_applied.any() and not world.data.xfrc_applied.any()
        angles.append(world.data.qpos[world.hinge_q])
    assert angles[0] < -0.03 and angles[1] > 0.03


def test_returning_to_center_fails_but_counterbalancing_can_leave_center_and_succeed(world):
    world.reset(0)
    centered = rollout(world, SeesawWorld.center_action)
    assert not centered["success"] and centered["balance_fraction"] < 0.3
    world.reset(0)
    weights, positions = [], []
    while not world.done:
        _, _, _, _, result = world.step(SeesawWorld.rule_action(world.observation()))
        weights.append(result["weight_position_m"])
        positions.append(result["position_m"])
    assert result["success"] and result["balance_fraction"] >= 0.7
    assert min(weights) < -0.25 and max(weights) > 0.25
    assert min(positions) < -0.08 and max(positions) > 0.08
    assert "center" not in result["reward_terms"]
    # No hidden center constraint remains in the success gate.
    assert abs(result["position_m"]) > 0.035


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
        if backend.world.data.time >= 1.5:
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
    assert data.time == 0 and data.qpos[backend.world.slider_q] == 0
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
    # An upgrade must reject the static board's valid but incompatible bundle.
    with pytest.raises(ValueError, match="匹配"):
        SeesawArtifacts(directory / "static-v2").policy("trained", world.manifest())
    policy = artifacts.policy("trained", world.manifest())
    assert policy.steps == artifacts.report()["selected_steps"]
    # Replay recorded held-out episodes. A changed model/actor
    # must not silently keep claiming the outcomes in an older report.
    rows = {row["seed"]: row for row in artifacts.report()["test"]["results"]}
    for seed in (30000, 30025):
        world.reset(seed)
        info = rollout(world, policy)
        assert info["seconds"] <= DURATION + 1e-6
        assert info["success"] == rows[seed]["success"]
        assert info["reason"] == rows[seed]["reason"]

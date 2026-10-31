"""Real disk dynamics and bounded coach execution, not tests of painted poses."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import mujoco
import numpy as np
import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.balance import BalanceConfig, BalanceWorld, point_velocity
from duckking.balance_backend import BalanceBackend
from duckking.balance_policy import BalancePolicy
from duckking.balance_runs import BalanceRuns
from duckking.config import Settings
from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController
from duckking.voice import VoiceSession

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture(scope="module")
def world():
    return BalanceWorld(ASSETS)


def test_real_disk_has_inertia_motor_limits_and_no_robot_body_forces(world):
    world.config = BalanceConfig(level=1)
    world.reset(0)
    for _ in range(50):
        _, _, _, _, info = world.step(np.zeros(3))
    assert not world.done
    assert abs(info["rpm"]) > 1
    assert info["contacts"] > 0
    assert world.model.body_mass[world.disc] >= 2
    assert world.model.body_mocapid[world.disc] == -1
    assert not np.any(world.data.xfrc_applied)
    assert not np.any(world.data.qfrc_applied)
    assert np.all(np.abs(world.data.actuator_force[world.disc_act]) <= [25.001, 25.001, 12.001])
    assert info["rim_margin"] > 0


def test_stop_physically_decelerates_then_terminates_without_success(world):
    world.config = BalanceConfig(level=1)
    world.reset(0)
    for _ in range(30):
        world.step(np.zeros(3))
    before = float(world.data.time)
    world.request_stop()
    velocities = []
    while not world.done:
        _, _, _, _, info = world.step(np.zeros(3))
        velocities.append(info["rpm"])
    assert 2.9 <= world.data.time - before <= 3.1
    assert info["disk_stopped"] and not info["success"]
    assert info["reason"] == "cancelled"
    assert abs(velocities[0]) > abs(velocities[-1])
    with pytest.raises(RuntimeError, match="已结束"):
        world.step(np.zeros(3))


def test_pose_hacking_falls_rim_escape_and_nan_actions_are_rejected(world):
    world.reset(9)
    with pytest.raises(ValueError, match="无效动作"):
        world.step([float("nan"), 0, 0])
    assert world.steps == 0
    world.data.qpos[world.driver.root] = 0.4
    mujoco.mj_forward(world.model, world.data)
    assert world.measure()["rim_margin"] < 0
    _, _, terminated, _, info = world.step(np.zeros(3))
    assert terminated and not info["success"]
    world.reset(9)
    world.data.qpos[world.driver.root + 3 : world.driver.root + 7] = [0, 1, 0, 0]
    mujoco.mj_forward(world.model, world.data)
    _, _, terminated, _, info = world.step(np.zeros(3))
    assert terminated and not info["success"]


def test_same_seed_reproduces_physics_and_all_levels_have_distinct_goals(world):
    starts = []
    for level in (1, 2, 3):
        world.config = BalanceConfig(level=level)
        world.reset(5)
        starts.append(world.measure()["radius"])
    assert starts[2] > starts[1] * 4
    world.config = BalanceConfig(level=2)
    results = []
    for _ in range(2):
        world.reset(11)
        for _ in range(15):
            world.step([0.1, 0, -0.1])
        results.append(world.data.qpos.copy())
    np.testing.assert_array_equal(*results)


def test_point_velocity_and_actor_velocity_use_the_same_regular_body_frame(world):
    world.reset(42)
    world.data.qvel[:] = np.random.default_rng(53).normal(0, 0.2, world.model.nv)
    mujoco.mj_forward(world.model, world.data)
    jp, jr = np.zeros((3, world.model.nv)), np.zeros((3, world.model.nv))
    for body in (world.driver.body, world.disc, int(world.model.geom_bodyid[world.feet[0]])):
        point = world.data.xpos[body] + [0.04, -0.03, 0.01]
        mujoco.mj_jac(world.model, world.data, jp, jr, point, body)
        np.testing.assert_allclose(
            point_velocity(world.model, world.data, body, point), jp @ world.data.qvel, atol=1e-12
        )
    body = world.driver.body
    mujoco.mj_jacBody(world.model, world.data, jp, jr, body)
    rotation = world.data.xmat[body].reshape(3, 3)
    obs = world.observation()
    np.testing.assert_allclose(rotation @ obs[7:10], jr @ world.data.qvel, atol=1e-7)
    np.testing.assert_allclose(rotation @ obs[10:13], jp @ world.data.qvel, atol=1e-7)


def test_artifact_rejects_wrong_level_model_or_invalid_weights(tmp_path, world):
    manifest = world.manifest()
    path = tmp_path / "policy.json"
    payload = {
        "contract": manifest["contract"],
        "model_sha256": "wrong",
        "level": manifest["config"]["level"],
        "steps": 0,
        "layers": [],
    }
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="不兼容"):
        BalancePolicy(path, manifest)
    payload["model_sha256"] = manifest["model_sha256"]
    payload["layers"] = [
        {"weight": [[float("nan")] * manifest["observation_size"]], "bias": [0]}
    ] * 3
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="无效 PPO"):
        BalancePolicy(path, manifest)


@pytest.fixture
def backend(tmp_path, monkeypatch, world):
    # Reuse compiled geometry/session, but all dynamic state belongs to the new room.
    def create(assets):
        return BalanceWorld(
            assets, compiled=(world.model, world.fingerprint), session=world.session
        )

    monkeypatch.setattr("duckking.balance_backend.BalanceWorld", create)
    return BalanceBackend(ASSETS, BalanceRuns(tmp_path, tmp_path / "bundled"))


async def test_missing_ppo_never_falls_back_and_ordinary_motions_are_rejected(backend):
    with pytest.raises(ValueError, match="尚无"):
        await backend.invoke({"operation": "start", "level": 2})
    assert backend.task is None and backend.phase == "idle"
    with pytest.raises(ValueError, match="不能叠加"):
        await backend.prepare(Action(name="walk"))
    with pytest.raises(ValueError):
        await backend.invoke({"operation": "start", "level": True, "controller": "baseline"})


async def test_live_stop_serializes_physics_and_reset_does_not_revive_actions(backend):
    await backend.invoke({"operation": "start", "controller": "baseline", "seed": 0})
    await asyncio.sleep(0.15)
    state = await backend.snapshot()
    assert len(state["observation"]) == 25
    assert len(state["task_action"]) == 3
    await asyncio.wait_for(backend.stop(), 6)
    assert backend.task.done()
    assert backend.summary()["phase"] == "cancelled"
    await backend.reset()
    await asyncio.sleep(0.15)
    assert backend.world.data.time == 0
    await backend.close()


async def test_stop_supersedes_a_start_waiting_for_previous_deceleration(backend, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def halt():
        entered.set()
        await release.wait()

    monkeypatch.setattr(backend, "_halt", halt)
    pending = asyncio.create_task(backend.invoke({"operation": "start", "controller": "baseline"}))
    await entered.wait()
    stop = asyncio.create_task(backend.stop())
    await asyncio.sleep(0)
    release.set()
    await stop
    with pytest.raises(ValueError, match="取消"):
        await pending
    assert backend.task is None


async def test_select_prepares_correct_level_for_the_next_voice_command(backend):
    await backend.invoke({"operation": "select", "level": 3})
    assert backend.summary()["level"] == 3
    assert backend.phase == "idle" and backend.task is None
    assert backend.world.measure()["radius"] > 0.1
    with pytest.raises(ValueError):
        await backend.invoke({"operation": "status", "shell": "ignored?"})


async def test_balance_mcp_discovery_replay_and_protocol_failure(backend):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "test")
    listing = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert {t["name"] for t in listing["result"]["tools"]} == {
        "duck_stop",
        "duck_get_status",
        "duck_balance",
    }
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "duck_balance", "arguments": {"operation": "status"}},
    }
    assert await mcp.handle(request) == await mcp.handle(request)
    request["params"]["arguments"]["operation"] = "start"
    assert "error" in await mcp.handle(request)
    forbidden = await mcp.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "duck_walk_short"}}
    )
    assert forbidden["result"]["isError"]
    await motion.close()


async def test_new_utterance_preserves_balance_but_disconnect_stops_it(backend, tmp_path):
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


def test_training_read_api_has_no_path_escape_and_mutations_are_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKKING_BALANCE_RUNS", str(tmp_path / "runs"))
    monkeypatch.delenv("DUCKKING_BALANCE_TRAINING", raising=False)
    app = create_app(settings=Settings(data_dir=tmp_path / "private"))
    with TestClient(app) as client:
        assert not client.get("/api/balance/runs").json()["training_enabled"]
        assert client.post("/api/balance/train", json={"level": 1}).status_code == 409
        assert (
            client.post(
                "/api/balance/train",
                json={"level": 1},
                headers={"Origin": "https://attacker.invalid"},
            ).status_code
            == 403
        )
        assert client.get("/api/balance/runs/not-there").status_code == 404
        assert client.post("/api/balance/command", json={"operation": "start"}).status_code == 409
    store = BalanceRuns(tmp_path, tmp_path / "bundled")
    with pytest.raises(ValueError):
        store.directory("../private")


def test_truncated_metrics_are_tolerated_and_test_evidence_is_not_synthesized(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    (directory / "status.json").write_text('{"phase":"training","level":2}')
    (directory / "metrics.jsonl").write_text('{"steps":1024,"kind":"update"}\n{"steps":')
    store = BalanceRuns(tmp_path, tmp_path / "bundled")
    assert len(store.list()) == 1
    details = store.details("run")
    assert len(details["metrics"]) == 1
    assert details["test"] is None


async def test_training_launch_failure_is_terminal_and_never_stuck_preparing(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKKING_BALANCE_TRAINING", "1")
    monkeypatch.setenv("DUCKKING_TRAIN_PYTHON", str(tmp_path / "no-python"))
    store = BalanceRuns(tmp_path / "runs", tmp_path / "bundled")
    with pytest.raises(ValueError, match="解释器"):
        await store.launch(2, 16384, 42, ASSETS)
    assert store.list()[0]["phase"] == "failed"
    await store.close()


def policy_file(directory, world, *, steps=8192):
    directory.mkdir(parents=True, exist_ok=True)
    sizes = [world.manifest()["observation_size"], 64, 64, 3]
    payload = {
        "contract": world.manifest()["contract"],
        "model_sha256": world.fingerprint,
        "level": world.config.level,
        "steps": steps,
        "layers": [
            {"weight": np.zeros((out, inp)).tolist(), "bias": np.zeros(out).tolist()}
            for inp, out in zip(sizes[:-1], sizes[1:], strict=True)
        ],
    }
    path = directory / "best-policy.json"
    path.write_text(json.dumps(payload))
    return path, payload


def test_policy_bounds_and_corruption_fail_closed(tmp_path, world):
    path, payload = policy_file(tmp_path, world)
    payload["layers"][-1]["bias"] = [2, -2, 0.5]
    path.write_text(json.dumps(payload))
    policy = BalancePolicy(path, world.manifest())
    np.testing.assert_array_equal(policy(world.observation()), [1, -1, 0.5])
    for obs in ([0], [float("nan")] * 25):
        with pytest.raises(ValueError, match="观测"):
            policy(obs)
    for corrupt in (
        [],
        {"layers": None},
        {**payload, "steps": -1},
        {**payload, "layers": [{"weight": [], "bias": []}] * 3},
    ):
        path.write_text(json.dumps(corrupt))
        with pytest.raises(ValueError):
            BalancePolicy(path, world.manifest())
    path.write_text("{")
    with pytest.raises(ValueError, match="读取"):
        BalancePolicy(path, world.manifest())


async def test_valid_policy_executes_and_bad_inference_pauses_without_fallback(backend, tmp_path):
    path, _ = policy_file(tmp_path / "trained", backend.world)
    await backend.invoke({"operation": "start", "run": "trained"})
    await asyncio.sleep(0.15)
    assert backend.world.steps > 0
    assert backend.summary()["policy_steps"] == 8192
    assert backend.run_id == path.parent.name
    assert backend.controller == "trained"

    def broken(_):
        raise ValueError("injected invalid inference")

    backend.policy = broken
    await asyncio.wait_for(backend.task, 2)
    assert backend.phase == "failed"
    assert "invalid inference" in backend.error
    time = backend.world.data.time
    await asyncio.sleep(0.15)
    assert backend.world.data.time == time
    await backend.close()


async def test_running_balance_is_not_reallocated_as_an_idle_room(backend, tmp_path):
    from duckking.rooms import RoomRegistry

    app = create_app(settings=Settings(data_dir=tmp_path))
    room = app.state.rooms["1"]
    room.scene_motion = MotionController(backend)
    await backend.invoke({"operation": "start", "controller": "baseline"})
    assert RoomRegistry.busy(room)
    assert await app.state.room_registry.claim() == {"room": "2"}
    await backend.stop()
    assert not RoomRegistry.busy(room)
    await room.scene_motion.close()


def test_balance_api_preparation_is_room_scoped_and_voice_blocks_scene_replacement(
    backend, tmp_path, monkeypatch
):
    monkeypatch.setattr("duckking.balance_backend.BalanceBackend", lambda *_: backend)
    app = create_app(settings=Settings(data_dir=tmp_path, max_physics_rooms=1))
    with TestClient(app) as client:
        result = client.post("/api/balance/prepare?room=1", json={})
        assert result.status_code == 200
        assert result.json()["backend"]["scene"] == "balance"
        assert client.post("/api/balance/prepare?room=1", json={}).status_code == 200
        assert client.post("/api/balance/prepare?room=2", json={}).status_code == 409
        assert client.get("/api/scenes/model?room=1").status_code == 200
        assert client.get("/api/studio?room=1").status_code == 409
        for body in (
            {"operation": []},
            {"operation": "start", "controller": []},
            {"operation": "start", "level": 4},
        ):
            assert client.post("/api/balance/command?room=1", json=body).status_code == 422
        assert (
            client.post("/api/balance/command", json={"operation": "select", "level": 3}).json()[
                "level"
            ]
            == 3
        )
        with client.websocket_connect("/scene-voice?room=1") as ws:
            assert ws.receive_json()["state"] == "disconnected"
            assert (
                client.post("/api/scenes/start?room=1", json={"name": "scene_ball"}).status_code
                == 409
            )
            assert (
                client.post("/api/balance/command", json={"operation": "status"}).json()["level"]
                == 3
            )
        assert app.state.rooms["2"].scene_motion is None


async def test_training_worker_exit_and_cancel_are_owned_and_terminal(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("DUCKKING_BALANCE_TRAINING", "1")
    process = SimpleNamespace(
        returncode=None, wait=AsyncMock(return_value=2), terminate=lambda: None
    )
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    store = BalanceRuns(tmp_path / "runs", tmp_path / "bundled")
    for values in ((4, 16384, 42), (1, 10, 42), (1, 16384, -1)):
        with pytest.raises(ValueError):
            await store.launch(*values, ASSETS)
    job = await store.launch(2, 16384, 42, ASSETS)
    with pytest.raises(ValueError, match="已有"):
        await store.launch(2, 16384, 42, ASSETS)
    with pytest.raises(ValueError):
        await store.cancel("some-other-run")
    assert (await store.cancel(job["id"]))["phase"] == "cancelling"
    await store.watcher
    assert store.details(job["id"])["status"]["phase"] == "failed"
    process.returncode = 2
    await store.close()
    args, kwargs = launch.call_args
    assert args[1].endswith("training/train_balance.py")
    assert kwargs["env"]["OMP_NUM_THREADS"] == "1"
    assert kwargs["start_new_session"] is True


async def test_cancel_during_python_import_is_cancelled_instead_of_crashed(tmp_path, monkeypatch):
    import signal
    from types import SimpleNamespace

    monkeypatch.setenv("DUCKKING_BALANCE_TRAINING", "1")
    exited = asyncio.Event()

    async def wait():
        await exited.wait()
        return -signal.SIGTERM

    process = SimpleNamespace(returncode=None, wait=wait, terminate=exited.set)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    store = BalanceRuns(tmp_path / "runs", tmp_path / "bundled")
    job = await store.launch(2, 16384, 42, ASSETS)
    await store.cancel(job["id"])
    await store.watcher
    record = store.details(job["id"])
    assert record["status"]["phase"] == "cancelled"
    assert record["manifest"] is None and record["test"] is None
    assert record["metrics"] == []
    assert not store.cancel_requested
    process.returncode = -signal.SIGTERM
    await store.close()

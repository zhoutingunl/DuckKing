"""Real CPU MuJoCo contacts, plus controller and failure boundaries (no cloud calls)."""

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app
from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.simulation import MuJoCoBackend

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
def backend():
    return MuJoCoBackend(ASSETS)


@pytest.mark.parametrize("foot", ["left", "right"])
async def test_official_kicks_have_selected_foot_contact_and_measured_ball_motion(backend, foot):
    motion = MotionController(backend)
    action = Action(name=f"kick_{foot}")
    await motion.submit(action)
    result = await motion.wait(action.request_id)
    assert result["status"] == "completed"
    assert result["outcome"]["verified"]
    assert foot in result["outcome"]["contact_feet"]
    assert result["outcome"]["displacement_m"] > 0.02
    state = await backend.snapshot()
    assert state["physics"] is True and state["runtime"] == "mujoco_cpu_onnx"
    assert not state["ducks"][0]["fallen"]
    await motion.close()


async def test_ducks_share_contacts_and_discovery_requires_range_fov_and_line_of_sight(backend):
    backend.load("duo")
    assert len(backend.discover()) == 2
    assert backend.ball_state() is None
    initial = [d.pose(backend.data)[0].copy() for d in backend.drivers]
    for d in backend.drivers:
        d.command[0] = 0.25
    for _ in range(150):
        backend.tick()
    assert backend.contacts["ducks"] > 0
    assert all(
        np.linalg.norm(d.pose(backend.data)[0] - p) > 0.05
        for d, p in zip(backend.drivers, initial, strict=True)
    )
    backend.load("duo")
    driver = backend.drivers[1]
    backend.data.qpos[driver.root] = 5
    assert backend.discover() == []
    backend.data.qpos[driver.root] = -0.5
    backend.data.qpos[driver.root + 3 : driver.root + 7] = [1, 0, 0, 0]
    import mujoco

    mujoco.mj_forward(backend.model, backend.data)
    assert not any(row["observer"] == "a" for row in backend.discover())
    # Both look away, so close range alone cannot produce discovery.
    backend.data.qpos[driver.root + 3 : driver.root + 7] = [0, 0, 0, 1]
    mujoco.mj_forward(backend.model, backend.data)
    assert backend.discover() == []
    await backend.close()


async def test_stop_cancels_both_ducks_and_chorus_and_replay_does_not_restart(backend):
    backend.load("duo")
    motion = MotionController(backend)
    walk = Action(name="duo_walk")
    await motion.submit(walk)
    await asyncio.sleep(0.07)
    assert all(d.command[0] > 0 for d in backend.drivers)
    assert (await motion.submit(walk))["id"] == walk.request_id
    stop = Action(name="stop")
    await motion.submit(stop)
    assert (await motion.wait(walk.request_id))["status"] == "cancelled"
    await motion.wait(stop.request_id)
    assert all(not d.command.any() for d in backend.drivers)
    sing = Action(name="chorus")
    await motion.submit(sing)
    await asyncio.sleep(0.08)
    state = await backend.snapshot()
    assert state["chorus"]["parts"] == 2 and state["chorus"]["source"] == "local_synth"
    change = Action(name="scene_ball")
    await motion.submit(change)
    await motion.wait(change.request_id)
    assert (await motion.wait(sing.request_id))["status"] == "cancelled"
    assert backend.chorus is None and len(backend.drivers) == 1
    await motion.close()


async def test_target_selection_reset_and_wrong_scene_fail_explicitly(backend):
    motion = MotionController(backend)
    for action in [Action(name="walk", target="b"), Action(name="collide")]:
        await motion.submit(action)
        assert (await motion.wait(action.request_id))["status"] == "failed"
    backend.load("duo")
    await backend.prepare(Action(name="walk", target="b"))
    await backend.move(0.1, 0.2, 0.03)
    await backend.head(0.1, 0.2, 0.1)
    await backend.body_pose(0.005, 0.1, 0.1, True)
    assert backend.drivers[0].command.tolist() == [0] * 13
    assert backend.drivers[1].command[0] == pytest.approx(0.1)
    await backend.body_pose(0, 0, 0, False)
    await backend.prepare(Action(name="walk", target="both"))
    await backend.move(0.1, 0)
    assert all(d.command[0] > 0 for d in backend.drivers)
    kick = Action(name="kick_left")
    await motion.submit(kick)
    assert (await motion.wait(kick.request_id))["status"] == "failed"
    await backend.reset()
    assert all(not d.command.any() for d in backend.drivers)
    geometry = backend.geometry()
    assert geometry["revision"] == (await backend.snapshot())["revision"]
    assert geometry["meshes"] and len(geometry["geoms"]) > 100
    await motion.close()


async def test_physics_failure_is_visible_and_reset_recovers(backend, monkeypatch):
    original = backend.tick
    monkeypatch.setattr(backend, "tick", lambda: (_ for _ in ()).throw(ValueError("solver")))
    backend.start()
    await asyncio.sleep(0.03)
    assert (await backend.snapshot())["connected"] is False
    with pytest.raises(ValueError, match="推进失败"):
        await backend.prepare(Action(name="walk"))
    with pytest.raises(ValueError, match="推进失败"):
        await backend.wait_sim(0.2)
    monkeypatch.setattr(backend, "tick", original)
    await backend.reset()
    assert (await backend.snapshot())["connected"] is True
    await backend.close()


async def test_solver_failure_during_motion_does_not_report_completed(backend, monkeypatch):
    motion = MotionController(backend)
    action = Action(name="walk")
    await motion.submit(action)
    await asyncio.sleep(.03)
    monkeypatch.setattr(backend, "tick", lambda: (_ for _ in ()).throw(ValueError("solver")))
    result = await motion.wait(action.request_id)
    assert result["status"] == "failed"
    assert "推进失败" in result["error"]
    assert all(not driver.command.any() for driver in backend.drivers)
    await motion.close()


async def test_mcp_scene_schema_left_right_required_and_failed_contact_is_not_success(backend):
    motion = MotionController(backend)
    mcp = DeviceMCP(motion, "physical-test")

    async def call(name, arguments=None, ident=1):
        return await mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )

    listing = await mcp.handle({"jsonrpc": "2.0", "id": "list", "method": "tools/list"})
    names = {t["name"] for t in listing["result"]["tools"]}
    assert {"duck_kick", "duck_set_scene", "duck_chorus"} <= names
    assert (await call("duck_kick"))["result"]["isError"]
    assert (await call("duck_set_scene", {"scene": "invalid"}, 2))["result"]["isError"]
    assert (await call("duck_set_scene", {"scene": "duo"}, 3))["result"]["isError"] is False
    assert (await call("duck_find_companion", ident=4))["result"]["isError"] is False
    assert (await call("duck_kick", {"foot": "left"}, 5))["result"]["isError"] is True
    assert (await call("duck_collide", ident=6))["result"]["isError"] is False
    assert (await call("duck_chorus", ident=7))["result"]["isError"] is False
    status = await call("duck_get_status", ident=8)
    assert "geoms" not in json.loads(status["result"]["content"][0]["text"])["backend"]
    await motion.close()


async def test_scenarios_never_fall_back_to_preview():
    motion = MotionController(PreviewBackend())
    action = Action(name="kick_left")
    await motion.submit(action)
    assert (await motion.wait(action.request_id))["status"] == "failed"
    await motion.close()


async def test_missed_ball_reports_failure_instead_of_success(backend, monkeypatch):
    def misplaced_ball(foot):
        backend.ball_start = np.array([4, 4, 0.035])
        adr = backend.model.jnt_qposadr[backend.model.joint("ball_free").id]
        backend.data.qpos[adr : adr + 3] = backend.ball_start

    async def advance(duration):
        for _ in range(round(duration / 0.02)):
            backend.tick()

    monkeypatch.setattr(backend, "place_ball", misplaced_ball)
    monkeypatch.setattr(backend, "wait_sim", advance)
    motion = MotionController(backend)
    action = Action(name="kick_left")
    await motion.submit(action)
    result = await motion.wait(action.request_id)
    assert result["status"] == "failed"
    assert result["outcome"]["verified"] is False
    assert result["outcome"]["contacts"] == 0
    await motion.close()


@pytest.mark.parametrize(
    "body",
    [
        {"name": "kick_left", "duration": 0.2},
        {"name": "chorus", "duration": 99},
        {"name": "duo_walk", "speed": 0.3},
        {"name": "walk", "target": "c"},
    ],
)
def test_scene_actions_remain_bounded(body):
    with pytest.raises(ValidationError):
        Action(**body)


def test_scene_http_websocket_origin_model_and_missing_dependencies(monkeypatch):
    with TestClient(create_app()) as client:
        assert client.get("/api/scenes/state").status_code == 503
        with client.websocket_connect("/scene-ws") as ws:
            assert ws.receive_json()["type"] == "not_started"
        with client.websocket_connect("/scene-voice") as ws:
            assert ws.receive_json()["error"] == "请先启动物理场景再连接灵矽"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/scene-ws", headers={"Origin": "https://bad.example"}):
                pass
        assert client.post("/api/scenes/start", json={"name": "walk"}).status_code == 422
        assert (
            client.post(
                "/api/scenes/start",
                json={"name": "scene_ball"},
                headers={"Origin": "https://bad.example"},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/scenes/start", json={"name": "scene_ball", "request_id": "load"}
        )
        assert response.status_code == 202
        assert (
            client.post(
                "/api/scenes/start", json={"name": "scene_duo", "request_id": "load"}
            ).status_code
            == 409
        )
        assert client.get("/api/scenes/model").json()["meshes"]
        assert client.get("/api/scenes/state").json()["backend"]["physics"] is True
        assert client.get("/api/scenes/actions/load").status_code == 200
        assert client.get("/api/scenes/actions/missing").status_code == 404
        with client.websocket_connect("/scene-ws") as ws:
            assert ws.receive_json()["backend"]["scene"] == "ball"
        assert (
            client.post("/api/scenes/actions", json={"name": "stop", "request_id": "s"}).status_code
            == 202
        )
        assert (
            client.post("/api/scenes/actions", json={"name": "nod", "request_id": "s"}).status_code
            == 409
        )
    monkeypatch.setenv("DUCKKING_SIM_DIR", "/does-not-exist-private-path")
    with TestClient(create_app()) as client:
        response = client.post("/api/scenes/start", json={"name": "scene_duo"})
        assert response.status_code == 503
        assert "private-path" not in response.text
        assert "setup_scenarios.sh" in response.text

"""Real contact grasping; faults deliberately perturb physical state, never cloud results."""

import asyncio
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from duckking.app import create_app
from duckking.mcp import DeviceMCP
from duckking.model_assets import official_preview
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.simulation import POLICY_JOINTS, MuJoCoBackend

ASSETS = Path(__file__).resolve().parents[1] / "external"


@pytest.fixture
async def motion():
    backend = MuJoCoBackend(ASSETS)
    backend.load("carry")
    controller = MotionController(backend)
    yield controller
    await controller.close()


async def execute(motion, name):
    action = Action(name=name)
    await motion.submit(action)
    return await motion.wait(action.request_id)


@pytest.mark.parametrize("idle", [0, 0.5, 2.0])
async def test_real_pick_carry_release_after_different_idle_times(motion, idle):
    backend = motion.backend
    backend.start()
    await asyncio.sleep(idle)
    assert backend.model.nu == 15
    assert len(backend.drivers[0].ids) == 14
    assert backend.model.neq == 0  # No attachment or weld constraint.
    for name in ("pick_up", "carry", "put_down"):
        result = await execute(motion, name)
        assert result["status"] == "completed", result
        outcome = result["outcome"]
        assert outcome["verified"] is True
        json.dumps(result)  # Public API and MCP must contain native JSON scalar types.
        if name == "pick_up":
            assert outcome["normal_force_n"]["upper"] > 0.01
            assert outcome["normal_force_n"]["lower"] > 0.01
            assert outcome["normal_force_n"]["source"] == 0
            assert outcome["lift_clearance_m"] > 0.008
            assert outcome["bilateral_s"] >= 0.2
            # Stopping a completed step must not open the mouth or lower the head.
            assert backend.grasp.held
            assert not backend.drivers[0].command[:3].any()
        elif name == "carry":
            assert outcome["carry_distance_m"] > 0.10
            assert outcome["robot_distance_m"] > 0.08
            assert outcome["max_slip_m"] < 0.018
        else:
            assert not outcome["held"]
            assert outcome["released_stable_s"] >= 0.2
            assert outcome["normal_force_n"]["upper"] + outcome["normal_force_n"]["lower"] < 0.001
            assert outcome["normal_force_n"]["destination"] > 0.005
        await asyncio.sleep(idle)
    assert not (await backend.snapshot())["ducks"][0]["fallen"]


async def test_cancel_carry_keeps_secured_object_and_reset_reopens(motion):
    assert (await execute(motion, "pick_up"))["status"] == "completed"
    action = Action(name="carry")
    await motion.submit(action)
    await asyncio.sleep(0.15)
    assert motion.backend.drivers[0].command[0] > 0
    assert (await execute(motion, "stop"))["status"] == "completed"
    assert (await motion.wait(action.request_id))["status"] == "cancelled"
    grasp = motion.backend.grasp
    assert grasp.phase == "interrupted"
    assert grasp.held and grasp.data.ctrl[grasp.mouth] < 0
    assert not motion.backend.drivers[0].command[:3].any()
    assert (await execute(motion, "reset"))["status"] == "completed"
    assert motion.backend.grasp.phase == "ready"
    assert not motion.backend.grasp.held
    assert motion.backend.grasp.data.ctrl[grasp.mouth] > 0.5


async def test_grasp_loss_is_detected_between_actions(motion):
    assert (await execute(motion, "pick_up"))["status"] == "completed"
    b = motion.backend
    # Simulated actuator fault: the jaw actually opens and loses contact.
    b.data.ctrl[b.grasp.mouth] = .524
    await asyncio.sleep(0.5)
    assert b.grasp.failure and not b.grasp.held
    result = await execute(motion, "carry")
    assert result["status"] == "failed"
    assert not b.drivers[0].command[:3].any()


async def test_missed_grasp_and_wrong_order_are_mcp_errors_and_do_not_move_object(motion):
    mcp = DeviceMCP(motion, "grasp-test")

    async def call(name, ident, args=None):
        return await mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            }
        )

    assert (await call("duck_carry", 1))["result"]["isError"]
    assert (await call("duck_put_down", 2))["result"]["isError"]
    assert (await call("duck_pick_up", 3, {"speed": 0.4}))["result"]["isError"]
    assert (await execute(motion, "walk"))["status"] == "failed"
    b = motion.backend
    q = b.model.jnt_qposadr[b.model.joint("object_free").id]
    b.data.qpos[q : q + 3] = [
        0.7,
        0.4,
        0.004,
    ]  # Deliberately remove the object from the pickup stand.
    mujoco.mj_forward(b.model, b.data)
    before = b.grasp.position()
    missed = await call("duck_pick_up", 4)
    assert missed["result"]["isError"]
    record = json.loads(missed["result"]["content"][0]["text"])
    assert record["outcome"]["verified"] is False
    assert np.linalg.norm(b.grasp.position()[:2] - before[:2]) < 0.01
    assert await call("duck_pick_up", 4) == missed  # Replay never retries the grasp.
    assert (await execute(motion, "scene_ball"))["status"] == "completed"
    assert (await execute(motion, "pick_up"))["status"] == "failed"
    await mcp.close()


async def test_grasp_timeout_and_cancel_during_closing(motion, monkeypatch):
    b = motion.backend
    action = Action(name="pick_up")
    await motion.submit(action)
    await asyncio.sleep(0.15)
    await execute(motion, "stop")
    assert (await motion.wait(action.request_id))["status"] == "cancelled"
    assert not b.grasp.held
    assert b.grasp.phase == "interrupted"
    await execute(motion, "reset")
    # A frozen physics clock must not leave a tool call pending indefinitely.
    monkeypatch.setattr(b, "tick", lambda: None)
    result = await asyncio.wait_for(execute(motion, "pick_up"), 6)
    assert result["status"] == "failed"
    assert "超时" in result["error"]


@pytest.mark.parametrize(
    "data",
    [
        {"name": "pick_up", "duration": 0.2},
        {"name": "carry", "duration": 4},
        {"name": "put_down", "duration": 99},
        {"name": "put_down", "speed": 0.4},
        {"name": "walk", "duration": 4.5},
        {"name": "scene_carry", "duration": 1},
    ],
)
def test_grasp_actions_have_fixed_bounded_durations(data):
    with pytest.raises(ValidationError):
        Action(**data)


async def test_grasp_is_never_exposed_as_preview_physics():
    motion = MotionController(PreviewBackend())
    assert (await execute(motion, "pick_up"))["status"] == "failed"
    listing = await DeviceMCP(motion, "preview-test").handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert "duck_pick_up" not in {tool["name"] for tool in listing["result"]["tools"]}
    await motion.close()


def test_official_preview_rig_api_and_missing_assets_are_explicit(monkeypatch):
    with TestClient(create_app()) as client:
        response = client.get("/api/models/microduck")
        assert response.status_code == 200
        model = response.json()
        assert model["physics"] is False
        assert model["source"] == "official_microduck_visuals"
        assert {j["name"] for b in model["bodies"] for j in b["joints"]} == set(POLICY_JOINTS)
        assert model["meshes"] and len(model["geoms"]) == 70
        assert client.get("/api/scenes/state").status_code == 503  # No simulation was started.
    monkeypatch.setenv("DUCKKING_SIM_DIR", "/missing-private-model-path")
    with TestClient(create_app()) as client:
        failed = client.get("/api/models/microduck")
        assert failed.status_code == 503 and "setup_scenarios.sh" in failed.text
        assert "private-model-path" not in failed.text
    official_preview.cache_clear()


async def test_release_without_receiving_support_is_failure(motion):
    assert (await execute(motion, "pick_up"))["status"] == "completed"
    assert (await execute(motion, "carry"))["status"] == "completed"
    b = motion.backend
    tray = b.model.geom("destination_support").id
    b.model.geom_contype[tray] = b.model.geom_conaffinity[tray] = 0
    result = await execute(motion, "put_down")
    assert result["status"] == "failed"
    assert result["outcome"]["verified"] is False
    assert result["outcome"]["normal_force_n"]["destination"] == 0
    assert not b.drivers[0].command[:3].any()


async def test_mujoco_automatic_reset_is_reported_as_physics_failure(motion, monkeypatch):
    b = motion.backend
    def reset_clock(model, data):
        data.time = 0
    monkeypatch.setattr(mujoco, "mj_step", reset_clock)
    b.start()
    await asyncio.sleep(.04)
    assert (await b.snapshot())["connected"] is False
    assert (await execute(motion, "pick_up"))["status"] == "failed"

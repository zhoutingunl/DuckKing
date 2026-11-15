"""World-family transitions; the standard world here is a protocol fixture."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.feature_api import Selection
from duckking.feature_backend import FeatureBackend
from duckking.motion import Action, MotionController, PreviewBackend


class StandardWorld(PreviewBackend):
    kind = "mujoco"
    scene = "ball"

    async def prepare(self, action):
        pass

    async def perform(self, action):
        self.scene = action.name.removeprefix("scene_")
        return {"verified": True}

    async def snapshot(self):
        return {**await super().snapshot(), "scene": self.scene}


@pytest.fixture
def handoff(monkeypatch):
    app = create_app()
    with TestClient(app) as client:
        # FeatureBackend.close is real, including its pending-future cleanup.
        # Actual process termination and physical actions are checked in the browser regression.
        old = client.portal.call(FeatureBackend, "director")
        old.state = {"feature": {"status": "running"}}
        current = MotionController(old)
        room = app.state.rooms["1"]
        room.scene_motion = current

        def create(*args, **kwargs):
            assert old.closed and old.ready.cancelled()
            assert room.scene_motion is None
            return StandardWorld()

        factory = Mock(side_effect=create)
        monkeypatch.setattr("duckking.simulation.MuJoCoBackend", factory)
        yield app, client, old, current, factory
        room.voice = None


@pytest.mark.parametrize("status", ["running", "cancelled"])
@pytest.mark.parametrize("scene", [
    "ball", "duo", "choir", "carry", "table", "seated", "skills", "rollers", "stage",
])
def test_functional_world_is_released_before_any_standard_stage(handoff, status, scene):
    app, client, old, current, factory = handoff
    old.state["feature"]["status"] = status
    response = client.post("/api/scenes/start", json={"name": f"scene_{scene}"})
    assert response.status_code == 202
    assert app.state.rooms["1"].scene_motion is not current
    assert old.closed and factory.call_count == 1
    replacement = app.state.rooms["1"].scene_motion
    result = client.portal.call(replacement.wait, response.json()["id"])
    assert result["status"] == "completed"
    assert client.get("/api/scenes/state").json()["backend"]["scene"] == scene
    assert replacement.studio is not None


def test_voice_conflict_preserves_old_world_then_allows_switch_after_disconnect(handoff):
    app, client, old, current, factory = handoff
    room = app.state.rooms["1"]
    room.voice = object()  # A busy-session marker; no cloud or microphone involved.
    response = client.post("/api/scenes/start", json={"name": "scene_ball"})
    assert response.status_code == 409 and "断开" in response.json()["detail"]
    assert room.scene_motion is current and not old.closed
    factory.assert_not_called()
    room.voice = None
    assert client.post("/api/scenes/start", json={"name": "scene_ball"}).status_code == 202
    assert old.closed


def test_failed_replacement_leaves_no_old_world_and_can_retry_without_preview(handoff):
    app, client, old, current, factory = handoff
    create = factory.side_effect
    factory.side_effect = RuntimeError("private build error")
    response = client.post("/api/scenes/start", json={"name": "scene_ball"})
    assert response.status_code == 503 and "private" not in response.text
    assert old.closed and app.state.rooms["1"].scene_motion is None
    assert app.state.rooms["1"].preparing is None
    factory.side_effect = create
    response = client.post("/api/scenes/start", json={"name": "scene_duo"})
    assert response.status_code == 202
    replacement = app.state.rooms["1"].scene_motion
    result = client.portal.call(replacement.wait, response.json()["id"])
    assert result["status"] == "completed" and replacement.backend.kind == "mujoco"


async def test_real_director_worker_exits_before_demo_can_start(
    direct_room_visitor,
):
    app = create_app()
    endpoint = {route.path: route.endpoint for route in app.routes if hasattr(route, "endpoint")}
    old = None
    try:
        await endpoint["/api/features/prepare"](Selection(capability="director"), "1")
        old = app.state.rooms["1"].scene_motion.backend
        await old.invoke({"action": "conduct", "order": ["a", "b", "c", "d"]})
        assert old.process.returncode is None
        assert old.state["feature"]["status"] == "running"
        record = await endpoint["/api/scenes/start"](Action(name="scene_ball"), "1")
        assert old.closed and old.process.returncode is not None and old.reader.done()
        current = app.state.rooms["1"].scene_motion
        assert (await current.wait(record["id"]))["status"] == "completed"
        assert current.backend.scene == "ball"
        action = await current.submit(Action(name="nod"))
        assert (await current.wait(action["id"]))["status"] == "completed"
    finally:
        await endpoint["/api/scenes/close"]("1", False)
        if old:
            await old.close()

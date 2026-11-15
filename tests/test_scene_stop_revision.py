from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from duckking.app import create_app


def test_version_guard_does_not_stop_a_new_world_and_preserves_the_current_world():
    app = create_app()
    with TestClient(app) as client:
        current = SimpleNamespace(
            backend=SimpleNamespace(revision="new-world"),
            submit=AsyncMock(return_value={"id": "s", "status": "running"}), close=AsyncMock(),
        )
        app.state.rooms["1"].scene_motion = current
        response = client.post(
            "/api/scenes/actions?expected_revision=old-world", json={"name": "stop"}
        )
        assert response.status_code == 409 and response.json()["detail"]["code"] == "scene_changed"
        current.submit.assert_not_awaited()
        assert app.state.rooms["1"].scene_motion is current
        for version in ("", "x" * 101):
            response = client.post(
                "/api/scenes/actions", params={"expected_revision": version}, json={"name": "stop"}
            )
            assert response.status_code == 422
        current.submit.assert_not_awaited()
        response = client.post(
            "/api/scenes/actions?expected_revision=new-world", json={"name": "stop"}
        )
        assert response.status_code == 202
        assert current.submit.await_args.args[0].name == "stop"
        assert app.state.rooms["1"].scene_motion is current


def test_guarded_stop_has_a_bounded_lock_wait_and_no_late_submission(monkeypatch):
    monkeypatch.setattr("duckking.app.SCENE_ACTION_GUARD_TIMEOUT", .02)
    app = create_app()
    with TestClient(app) as client:
        room = app.state.rooms["1"]
        room.scene_motion = SimpleNamespace(
            backend=SimpleNamespace(revision="r"), submit=AsyncMock(), close=AsyncMock(),
        )
        client.portal.call(room.scene_lock.acquire)
        try:
            response = client.post("/api/scenes/actions?expected_revision=r", json={"name": "stop"})
            assert response.status_code == 504 and "停止尚未确认" in response.json()["detail"]
        finally:
            room.scene_lock.release()
        room.scene_motion.submit.assert_not_awaited()

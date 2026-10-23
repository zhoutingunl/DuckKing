import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app, main


def test_http_action_and_real_state_stream():
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["backend"] == "preview"
        response = client.post("/api/actions", json={"name": "walk", "duration": 0.2})
        assert response.status_code == 202
        with client.websocket_connect("/ws") as ws:
            frame = ws.receive_json()
            assert frame["type"] == "state"
            assert frame["backend"]["physics"] is False
        assert client.post("/api/actions", json={"name": "stop"}).status_code == 202


def test_cross_origin_motion_is_rejected():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/actions", json={"name": "walk"}, headers={"Origin": "https://untrusted.example"}
        )
        assert response.status_code == 403
        assert (
            client.post("/api/actions", json={"name": "walk", "duration": 999}).status_code == 422
        )


def test_results_conflicts_unknown_ids_and_origin_websocket():
    with TestClient(create_app()) as client:
        body = {"name": "stop", "request_id": "unique"}
        client.post("/api/actions", json=body)
        assert client.get("/api/actions/unique").json()["name"] == "stop"
        assert client.get("/api/actions/missing").status_code == 404
        assert client.post("/api/actions", json=body | {"name": "nod"}).status_code == 409
        assert client.get("/api/state").json()["backend"]["kind"] == "preview"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"Origin": "https://bad.example"}):
                pass
        assert client.get("/api/health", headers={"Host": "bad.example"}).status_code == 400


def test_missing_build_explains_setup_and_built_assets_are_served(tmp_path, monkeypatch):
    monkeypatch.setattr("duckking.app.ROOT", tmp_path)
    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 503
    static = tmp_path / "frontend" / "dist"
    static.mkdir(parents=True)
    (static / "index.html").write_text("<h1>DuckKing</h1>")
    with TestClient(create_app()) as client:
        assert "DuckKing" in client.get("/").text


def test_cli_binds_loopback(monkeypatch):
    captured = {}
    monkeypatch.setattr("sys.argv", ["duckking", "--port", "9999"])
    monkeypatch.setattr("duckking.app.uvicorn.run", lambda app, **kw: captured.update(kw))
    main()
    assert captured == {"host": "127.0.0.1", "port": 9999}

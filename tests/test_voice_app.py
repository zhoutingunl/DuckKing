import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app, main
from duckking.config import Settings


def test_voice_websocket_activation_errors_and_disconnect(tmp_path, monkeypatch):
    async def activation(*args):
        return {"activation": {"code": "123456"}}

    monkeypatch.setattr("duckking.voice.provision", activation)
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with client.websocket_connect("/voice") as ws:
            assert ws.receive_json()["state"] == "disconnected"
            ws.send_json({"type": "connect"})
            assert ws.receive_json()["state"] == "connecting"
            assert ws.receive_json()["activation_code"] == "123456"
            ws.send_json({"type": "listen_start"})
            assert ws.receive_json()["type"] == "error"
            ws.send_json({"type": "listen_stop"})
            ws.send_bytes(b"ignored before listening")
            for data in [{"type": "unknown"}, ["not-an-object"]]:
                ws.send_json(data)
                assert ws.receive_json()["type"] == "error"
            ws.send_text("invalid json")
            assert ws.receive_json()["type"] == "error"
            ws.send_json({"type": "disconnect"})
            assert ws.receive_json()["state"] == "disconnected"


def test_voice_has_one_owner_and_rejects_cross_origin(tmp_path):
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/voice", headers={"Origin": "https://bad.example"}):
                pass
        with client.websocket_connect("/voice") as first:
            first.receive_json()
            with client.websocket_connect("/voice") as second:
                assert second.receive_json()["state"] == "busy"


def test_cli_selects_robotd_without_silent_fallback(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "sys.argv", ["duckking", "--backend", "robotd", "--socket", "/tmp/test.sock"]
    )

    def run(app, **kwargs):
        captured["backend"] = app.state.motion.backend

    monkeypatch.setattr("duckking.app.uvicorn.run", run)
    main()
    assert captured["backend"].kind == "robotd"
    assert captured["backend"].path == "/tmp/test.sock"

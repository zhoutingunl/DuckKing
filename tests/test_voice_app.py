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


def test_diagnostics_survive_browser_disconnect_and_never_expose_payloads(tmp_path, monkeypatch):
    async def broken_audio(*args):
        raise OSError("private-token/private-device/private-transcript")

    monkeypatch.setattr("duckking.voice.VoiceSession.audio", broken_audio)
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        response = client.get("/api/voice/diagnostics")
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["state"] == "disconnected"
        assert client.get(
            "/api/voice/diagnostics", headers={"Origin": "https://untrusted.example"}
        ).status_code == 403
        with client.websocket_connect("/voice") as ws:
            ws.receive_json()
            ws.send_bytes(b"private-audio")
            assert ws.receive_json()["aborted"]
            assert ws.receive_json()["state"] == "error"
            snapshot = client.get("/api/voice/diagnostics").json()
            assert snapshot["state"] == "error"
            assert any(e["event"] == "command_error" for e in snapshot["events"])
        snapshot = client.get("/api/voice/diagnostics").json()
        assert snapshot["state"] == "disconnected"
        assert snapshot["events"]
        assert "private-" not in str(snapshot)
        assert "private-" not in (tmp_path / "voice.jsonl").read_text()


def test_manual_reset_route_and_disconnect_interrupt_connect(tmp_path, monkeypatch):
    import asyncio

    async def slow_provision(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr("duckking.voice.provision", slow_provision)
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with client.websocket_connect("/voice") as ws:
            ws.receive_json()
            ws.send_json({"type": "connect"})
            assert ws.receive_json()["state"] == "connecting"
            ws.send_json({"type": "reset"})
            assert ws.receive_json()["aborted"]
            assert ws.receive_json()["state"] == "recovering"
            ws.send_json({"type": "disconnect"})
            assert ws.receive_json()["state"] == "disconnected"

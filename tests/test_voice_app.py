import asyncio
from types import SimpleNamespace

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


def test_explicit_disconnect_releases_owner_without_closing_the_page(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/voice") as first:
            assert first.receive_json()["state"] == "disconnected"
            first.send_json({"type": "disconnect"})
            assert first.receive_json()["state"] == "disconnected"
            with pytest.raises(WebSocketDisconnect):
                first.receive_json()
            assert app.state.voice is None
            # Keep the first browser context alive while the second claims voice.
            with client.websocket_connect("/voice") as second:
                assert second.receive_json()["state"] == "disconnected"
                assert app.state.voice is not None


def test_failed_cloud_connect_releases_owner_for_another_device(tmp_path, monkeypatch):
    async def unavailable(*args):
        raise OSError("private-device-token")

    monkeypatch.setattr("duckking.voice.provision", unavailable)
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/voice") as first:
            first.receive_json()
            first.send_json({"type": "connect"})
            assert first.receive_json()["state"] == "connecting"
            error = first.receive_json()
            assert error["state"] == "error" and "private-" not in str(error)
            with pytest.raises(WebSocketDisconnect):
                first.receive_json()
            assert app.state.voice is None
            with client.websocket_connect("/voice") as second:
                assert second.receive_json()["state"] == "disconnected"


def test_abandoned_browser_times_out_and_can_be_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr("duckking.app.VOICE_BROWSER_IDLE_TIMEOUT", 0.1)
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        with client.websocket_connect("/voice") as first:
            first.receive_json()
            with pytest.raises(WebSocketDisconnect):
                first.receive_json()
            assert app.state.voice is None
            assert any(e.get("reason") == "browser_idle"
                       for e in client.get("/api/voice/diagnostics").json()["events"])
            with client.websocket_connect("/voice") as second:
                assert second.receive_json()["state"] == "disconnected"
                second.send_json({"type": "ping"})
                assert second.receive_json() == {"type": "pong"}


async def test_concurrent_handshakes_cannot_both_reserve_voice(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    endpoint = next(route.endpoint for route in app.routes if route.path == "/voice")
    gate, entered = asyncio.Event(), asyncio.Event()

    class Socket:
        headers = {"host": "testserver"}
        url = SimpleNamespace(path="/voice")

        def __init__(self, blocked=False):
            self.blocked, self.sent, self.incoming = blocked, [], asyncio.Queue()

        async def accept(self):
            if self.blocked:
                entered.set()
                await gate.wait()

        async def send_json(self, message):
            self.sent.append(message)

        async def receive(self):
            return await self.incoming.get()

        async def close(self, code):
            pass

    first, second = Socket(blocked=True), Socket()
    task = asyncio.create_task(endpoint(first))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(endpoint(second), 1)
        assert second.sent[0]["state"] == "busy"
        reserved = app.state.voice
        assert reserved is not None
        gate.set()
        await first.incoming.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(task, 1)
        assert app.state.voice is None
    finally:
        gate.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await app.state.motion.close()


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
            assert snapshot["state"] == "disconnected"
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

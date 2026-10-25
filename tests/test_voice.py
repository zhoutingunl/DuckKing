import asyncio
import base64
import json

import pytest
from websockets.asyncio.server import serve

from duckking.config import Settings
from duckking.motion import MotionController, PreviewBackend
from duckking.opus import OpusCodec
from duckking.voice import VoiceSession


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():  # noqa: ASYNC110 - black-box protocol polling
            await asyncio.sleep(0.01)


def make_session(tmp_path, url="ws://127.0.0.1:1", **settings):
    messages = []

    async def send(data):
        messages.append(data)

    session = VoiceSession(
        send,
        MotionController(PreviewBackend()),
        Settings(data_dir=tmp_path, ws_url=url, ws_token="test-device-token", **settings),
    )
    return session, messages


async def test_real_local_websocket_opus_transcripts_and_tools(tmp_path):
    received = []
    release = asyncio.Event()

    async def cloud(ws):
        assert ws.request.headers["Authorization"] == "Bearer test-device-token"
        hello = json.loads(await ws.recv())
        assert hello["features"]["mcp"] is True
        assert hello["audio_params"]["sample_rate"] == 16000
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "transport": "websocket",
                    "session_id": "s1",
                    "audio_params": {"format": "opus", "sample_rate": 24000, "channels": 1},
                }
            )
        )
        assert json.loads(await ws.recv())["state"] == "start"
        packet = await ws.recv()
        decoder = OpusCodec(16000)
        assert len(decoder.decode(packet)) == 1920
        decoder.close()
        assert json.loads(await ws.recv())["state"] == "stop"
        for event in [
            {"type": "stt", "text": "点点头"},
            {"type": "tts", "state": "start"},
            {"type": "tts", "state": "sentence_start", "text": "收到指令"},
        ]:
            await ws.send(json.dumps(event))
        encoder = OpusCodec(24000)
        await ws.send(encoder.encode(bytes(2880)))
        encoder.close()
        await ws.send(
            json.dumps(
                {
                    "type": "mcp",
                    "payload": {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "duck_nod"},
                    },
                }
            )
        )
        received.append(json.loads(await ws.recv()))
        await ws.send(
            json.dumps(
                {
                    "type": "mcp",
                    "payload": {"jsonrpc": "2.0", "method": "notifications/initialized"},
                }
            )
        )
        await ws.send(json.dumps({"type": "tts", "state": "stop", "is_aborted": True}))
        await release.wait()

    async with serve(cloud, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        session, messages = make_session(tmp_path, f"ws://127.0.0.1:{port}")
        await session.open()
        assert session.state == "ready"
        await session.listen(True)
        await session.audio(bytes(1920))
        await session.listen(False)
        await eventually(lambda: bool(received))
        assert received[0]["payload"]["result"]["isError"] is False
        await eventually(lambda: session.state == "ready")
        assert any(m.get("role") == "user" for m in messages)
        audio = next(m for m in messages if m["type"] == "audio")
        assert len(base64.b64decode(audio["pcm"])) == 2880
        assert any(m.get("aborted") for m in messages)
        stats = session.diagnostics.statistics.snapshot()
        assert stats["counts"]["recognized"] == 1
        assert stats["counts"]["interrupted"] == 1
        assert stats["counts"]["completed_actions"] == 1
        assert stats["latencies"]["first_audio"]["count"] == 1
        assert stats["rounds"][0]["text"] == "点点头"
        release.set()
        await eventually(lambda: session.state == "disconnected")
        await session.disconnect()
        await session.motion.close()


@pytest.mark.parametrize(
    "hello",
    [
        {"type": "bad"},
        {"type": "hello", "transport": "websocket", "audio_params": {"channels": 2}},
        {"type": "hello", "transport": "websocket", "audio_params": {"format": "unknown"}},
    ],
)
async def test_bad_handshakes_fail_cleanly_without_exposing_credentials(tmp_path, hello):
    async def cloud(ws):
        await ws.recv()
        await ws.send(json.dumps(hello))
        await ws.wait_closed()

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, messages = make_session(
            tmp_path, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        )
        await session.open()
        assert session.state == "error"
        assert "test-device-token" not in json.dumps(messages)
        assert session.encoder is None
        await session.disconnect()


@pytest.mark.parametrize("payload", ["not-json", {"type": "mcp", "payload": []}, b"odd"])
async def test_malformed_downstream_data_reports_error_and_stops(tmp_path, payload):
    ready = asyncio.Event()

    async def cloud(ws):
        await ws.recv()
        await ws.send(
            json.dumps(
                {"type": "hello", "transport": "websocket", "audio_params": {"format": "pcm"}}
            )
        )
        await ready.wait()
        await ws.send(json.dumps(payload) if isinstance(payload, dict) else payload)
        await ws.wait_closed()

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, _ = make_session(tmp_path, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}")
        await session.open()
        ready.set()
        await eventually(lambda: session.state == "error")
        assert session.motion.current is None
        await session.disconnect()


async def test_activation_and_missing_token_and_network_failures(tmp_path, monkeypatch):
    session, messages = make_session(tmp_path)

    async def activation(*args):
        return {"activation": {"code": "654321"}}

    monkeypatch.setattr("duckking.voice.provision", activation)
    await session.open()
    assert session.state == "awaiting_binding"
    assert session.activation_code == "654321"

    async def missing(*args):
        return {"websocket": {"url": "wss://example.com/ws", "token": ""}}

    monkeypatch.setattr("duckking.voice.provision", missing)
    await session.open()
    assert session.state == "error"

    async def failed(*args):
        raise OSError("never-print-private-token")

    monkeypatch.setattr("duckking.voice.provision", failed)
    await session.open()
    assert "never-print-private-token" not in json.dumps(messages)
    await session.disconnect()


async def test_listening_guards_audio_bounds_deadline_and_tool_send_failure(tmp_path):
    session, _ = make_session(tmp_path)
    with pytest.raises(ValueError):
        await session.listen(True)
    with pytest.raises(ValueError):
        await session._json({})
    await session.listen(False)
    await session.audio(b"ignored while disconnected")

    class FakeCloud:
        def __init__(self):
            self.sent = []

        async def send(self, data):
            self.sent.append(data)

        async def close(self):
            pass

    session.cloud = FakeCloud()
    session.encoder = OpusCodec()
    session.state = "ready"
    await session.listen(True)
    with pytest.raises(ValueError):
        await session.audio(b"bad frame")
    session.started -= 16
    await session.audio(bytes(1920))
    assert session.state == "thinking"
    assert json.loads(session.cloud.sent[-1])["state"] == "stop"
    await session.disconnect()
    # No cloud: the tool handler must not turn a send error into a successful response.
    await session._tool({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})


async def test_valid_pcm_downstream_and_unknown_events(tmp_path):
    finish = asyncio.Event()

    async def cloud(ws):
        await ws.recv()
        await ws.send(
            json.dumps(
                {"type": "hello", "transport": "websocket", "audio_params": {"format": "pcm"}}
            )
        )
        await ws.send(bytes(640))
        await ws.send(json.dumps({"type": "unknown"}))
        await ws.send(json.dumps({"type": "tts", "state": "unknown"}))
        await finish.wait()

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, messages = make_session(
            tmp_path, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        )
        await session.open()
        await eventually(lambda: any(m["type"] == "audio" for m in messages))
        await session.disconnect()
        finish.set()

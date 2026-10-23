import asyncio
import json

import pytest
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from duckking.config import Settings
from duckking.diagnostics import VoiceDiagnostics
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.voice import VoiceSession


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():  # noqa: ASYNC110 - observe async protocol outcomes
            await asyncio.sleep(0.005)


@pytest.fixture
def deadlines(monkeypatch):
    monkeypatch.setattr("duckking.voice.WATCHDOG_INTERVAL", 0.01)
    monkeypatch.setattr("duckking.voice.RESPONSE_TIMEOUT", 0.08)
    monkeypatch.setattr("duckking.voice.PLAYBACK_TIMEOUT", 0.08)
    monkeypatch.setattr("duckking.voice.TURN_TIMEOUT", 0.4)


def session_for(tmp_path, port):
    messages = []

    async def send(data):
        messages.append(data)

    session = VoiceSession(
        send, MotionController(PreviewBackend()),
        Settings(data_dir=tmp_path, ws_url=f"ws://127.0.0.1:{port}", ws_token="private-token"),
        VoiceDiagnostics(tmp_path / "voice.jsonl"),
    )
    return session, messages


async def handshake(ws):
    await ws.recv()
    await ws.send(json.dumps({
        "type": "hello", "transport": "websocket", "session_id": "private-cloud-session",
        "audio_params": {"format": "pcm"},
    }))


@pytest.mark.parametrize("mode,reason", [
    ("silent", "response_idle"), ("speaking", "playback_idle"), ("activity", "turn_limit"),
])
async def test_stalled_turn_reconnects_once_stops_motion_and_never_replays_audio(
    tmp_path, deadlines, mode, reason,
):
    connections = []

    async def cloud(ws):
        received = []
        connections.append(received)
        await handshake(ws)
        if len(connections) > 1:
            async for packet in ws:
                received.append(packet)
            return
        async for packet in ws:
            received.append(packet)
            if isinstance(packet, str) and json.loads(packet).get("state") == "stop":
                if mode == "speaking":
                    await ws.send(json.dumps({"type": "tts", "state": "start"}))
                    await ws.send(bytes(640))
                if mode == "activity":
                    try:
                        while True:
                            await ws.send(json.dumps({"type": "stt", "text": "private-transcript"}))
                            await asyncio.sleep(0.02)
                    except ConnectionClosed:
                        return

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, messages = session_for(tmp_path, server.sockets[0].getsockname()[1])
        try:
            await session.open()
            first_encoder = session.encoder
            await session.listen(True)
            await session.audio(bytes(1920))
            record = await session.motion.submit(Action(name="walk", duration=3))
            await session.listen(False)
            await eventually(lambda: len(connections) == 2 and session.state == "ready")
            assert (await session.motion.wait(record["id"]))["status"] == "cancelled"
            assert first_encoder.encoder is None
            assert connections[1] == []
            assert any(m.get("aborted") for m in messages)
            assert any(m.get("state") == "recovering" for m in messages)
            events = session.diagnostics.snapshot()["events"]
            assert any(e.get("reason") == reason for e in events)
            assert session.diagnostic_status()["uplink_frames"] == 1
            log = (tmp_path / "voice.jsonl").read_text()
            assert "private-" not in log
            await asyncio.sleep(0.12)
            assert len(connections) == 2 and session.state == "ready"
        finally:
            await session.disconnect()
            await session.motion.close()


async def test_server_recording_deadline_works_without_more_audio(tmp_path, deadlines, monkeypatch):
    monkeypatch.setattr("duckking.voice.RECORDING_LIMIT", 0.04)
    stopped = asyncio.Event()

    async def cloud(ws):
        await handshake(ws)
        async for packet in ws:
            if json.loads(packet).get("state") == "stop":
                stopped.set()

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, _ = session_for(tmp_path, server.sockets[0].getsockname()[1])
        await session.open()
        await session.listen(True)
        await asyncio.wait_for(stopped.wait(), 1)
        assert session.state == "thinking"
        assert any(e.get("reason") == "recording_limit" for e in session.diagnostics.events)
        await session.disconnect()


async def test_connect_can_be_cancelled_while_ota_is_unresponsive(tmp_path, monkeypatch):
    entered = asyncio.Event()

    async def provision(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("duckking.voice.provision", provision)
    session, _ = session_for(tmp_path, 1)
    session.start_connect()
    await asyncio.wait_for(entered.wait(), 1)
    connector = session.connector
    session.start_connect()
    assert session.connector is connector
    await asyncio.wait_for(session.disconnect(), 1)
    assert connector.done()
    assert session.connector is None and session.state == "disconnected"


async def test_failed_recovery_stays_in_error_without_retry_loop(tmp_path, deadlines, monkeypatch):
    calls = 0

    async def cloud(ws):
        await handshake(ws)
        await ws.wait_closed()

    async with serve(cloud, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]

        async def provision(*args):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("private-token must never be logged")
            return {"websocket": {"url": f"ws://127.0.0.1:{port}", "token": "test"},
                    "identity": {"device_id": "test", "client_id": "test"}}

        monkeypatch.setattr("duckking.voice.provision", provision)
        session, messages = session_for(tmp_path, port)
        await session.open()
        await session.listen(True)
        await session.listen(False)
        await eventually(lambda: calls == 2 and session.state == "error")
        await asyncio.sleep(0.15)
        assert calls == 2
        assert session.cloud is None and session.encoder is None
        assert "private-token" not in json.dumps(messages)
        await session.disconnect()


async def test_manual_reset_cancels_inflight_tool_and_reconnects(tmp_path, deadlines):
    connections = 0
    trigger = asyncio.Event()

    async def cloud(ws):
        nonlocal connections
        connections += 1
        await handshake(ws)
        if connections == 1:
            await trigger.wait()
            await ws.send(json.dumps({"type": "mcp", "payload": {
                "jsonrpc": "2.0", "id": 42, "method": "tools/call",
                "params": {"name": "duck_walk_short", "arguments": {"duration": 3}},
            }}))
        await ws.wait_closed()

    async with serve(cloud, "127.0.0.1", 0) as server:
        session, _ = session_for(tmp_path, server.sockets[0].getsockname()[1])
        await session.open()
        trigger.set()
        await eventually(lambda: session.motion.current is not None)
        action_id = session.motion.current["id"]
        await session.reset(manual=True)
        await eventually(lambda: connections == 2 and session.state == "ready")
        assert not session.tasks
        assert session.motion.records[action_id]["status"] == "cancelled"
        assert any(e["event"] == "reset" for e in session.diagnostics.events)
        await session.disconnect()


async def test_watchdog_command_failure_is_safe_and_cleans_up(tmp_path, deadlines, monkeypatch):
    session, messages = session_for(tmp_path, 1)
    session.state = "listening"
    session.started = 0

    async def failed(*args):
        raise OSError("private details")

    monkeypatch.setattr(session, "listen", failed)
    session.watchdog = asyncio.create_task(session._watch())
    await eventually(lambda: session.state == "error")
    assert "private details" not in json.dumps(messages)
    assert any(m.get("aborted") for m in messages)
    await session.disconnect()


async def test_connection_has_overall_deadline(tmp_path, monkeypatch):
    async def slow_provision(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr("duckking.voice.provision", slow_provision)
    monkeypatch.setattr("duckking.voice.CONNECT_TIMEOUT", 0.03)
    session, _ = session_for(tmp_path, 1)
    await asyncio.wait_for(session.open(), 1)
    assert session.state == "error"
    assert "TimeoutError" in session.error
    await session.disconnect()


async def test_motion_stops_before_waiting_for_slow_cloud_close(tmp_path, monkeypatch):
    entered = asyncio.Event()

    class SlowCloud:
        async def close(self):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("duckking.voice.IO_TIMEOUT", 0.05)
    session, _ = session_for(tmp_path, 1)
    session.cloud = SlowCloud()
    record = await session.motion.submit(Action(name="walk", duration=3))
    cleanup = asyncio.create_task(session.disconnect())
    await asyncio.wait_for(entered.wait(), 1)
    assert session.motion.records[record["id"]]["status"] == "cancelled"
    await asyncio.wait_for(cleanup, 1)
    assert session.cloud is None
    await session.motion.close()

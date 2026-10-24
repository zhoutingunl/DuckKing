import asyncio
import json

import pytest
from test_voice_recovery import eventually, handshake, session_for
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from duckking.motion import Action


async def test_interrupt_stops_old_reply_and_motion_buffers_only_new_audio(tmp_path):
    connections = []
    gate = asyncio.Event()

    async def cloud(ws):
        received = []
        connections.append(received)
        number = len(connections)
        if number == 2:
            await gate.wait()
        await handshake(ws)
        try:
            async for packet in ws:
                received.append(packet)
                if isinstance(packet, str) and json.loads(packet).get('type') == 'abort':
                    # Deliberately deliver obsolete tool/audio frames after abort.
                    await ws.send(json.dumps({'type': 'tts', 'state': 'start'}))
                    await ws.send(bytes(640))
                    await ws.send(json.dumps({'type': 'mcp', 'payload': {
                        'jsonrpc': '2.0', 'id': 999, 'method': 'tools/call',
                        'params': {'name': 'duck_turn_right'},
                    }}))
        except ConnectionClosed:
            pass

    async with serve(cloud, '127.0.0.1', 0) as server:
        session, messages = session_for(tmp_path, server.sockets[0].getsockname()[1])
        other, _ = session_for(tmp_path / 'other', server.sockets[0].getsockname()[1])
        try:
            await session.open()
            old_mcp = session.mcp
            await old_mcp.handle({"jsonrpc": "2.0", "id": 44, "method": "initialize"})
            await session.listen(True)
            await session.audio(bytes(1920))
            await session.listen(False)
            first = await session.motion.submit(Action(name='walk', duration=3))
            other_action = await other.motion.submit(Action(name='turn_left', duration=3))
            session.start_interrupt()
            session.start_interrupt()  # Repeat while switching must not add a cloud connection.
            await session.listen(True)
            await session.audio(bytes([1, 0]) * 960)
            await session.audio(bytes([2, 0]) * 960)
            await session.listen(False)
            await session.audio(bytes(1920))  # Ignore post-release audio.
            await eventually(lambda: len(connections) == 2)
            assert (await session.motion.wait(first['id']))['status'] == 'cancelled'
            assert other.motion.records[other_action['id']]['status'] == 'running'
            gate.set()
            await eventually(lambda: session.state == 'thinking' and session.pending_input is None)
            assert len([p for p in connections[0] if isinstance(p, bytes)]) == 1
            assert len([p for p in connections[1] if isinstance(p, bytes)]) == 2
            controls = [json.loads(p) for p in connections[1] if isinstance(p, str)]
            assert [(p['type'], p.get('state')) for p in controls] == [
                ('listen', 'start'), ('listen', 'stop')]
            assert not any(m['type'] == 'audio' for m in messages)
            assert not any(r['name'] == 'turn_right' for r in session.motion.records.values())
            stats = session.diagnostics.statistics.snapshot()
            assert stats['counts']['interrupted'] == 1
            assert session.mcp is not old_mcp
            reused = await session.mcp.handle(
                {"jsonrpc": "2.0", "id": 44, "method": "tools/list"})
            assert "tools" in reused["result"]
            assert session.generation == 1 and session.uplink_frames == 2
            assert messages[-1]['generation'] == 1
        finally:
            gate.set()
            await session.disconnect()
            await other.disconnect()
            await session.motion.close()
            await other.motion.close()


async def test_interrupt_buffer_is_bounded_and_disconnect_drops_it(tmp_path):
    gate = asyncio.Event()
    connections = []

    async def cloud(ws):
        connections.append(ws)
        if len(connections) > 1:
            await gate.wait()
        try:
            await handshake(ws)
            await ws.wait_closed()
        except ConnectionClosed:
            pass

    async with serve(cloud, '127.0.0.1', 0) as server:
        session, _ = session_for(tmp_path, server.sockets[0].getsockname()[1])
        try:
            with pytest.raises(ValueError):
                session.start_interrupt()
            await session.open()
            session.start_interrupt()
            await session.audio(b'not-recording')
            await session.listen(True)
            with pytest.raises(ValueError):
                await session.audio(b'bad-pcm-frame')
            for _ in range(260):
                await session.audio(bytes(1920))
            assert len(session.pending_input['frames']) == 250
            assert session.pending_input['stopped']
            await session.disconnect()
            assert session.pending_input is None and session.connector is None
        finally:
            gate.set()
            await session.disconnect()
            await session.motion.close()


async def test_interruption_failure_is_explicit_and_does_not_replay(tmp_path, monkeypatch):
    async def cloud(ws):
        await handshake(ws)
        await ws.wait_closed()

    async with serve(cloud, '127.0.0.1', 0) as server:
        session, messages = session_for(tmp_path, server.sockets[0].getsockname()[1])
        try:
            await session.open()

            async def failed(*args, **kwargs):
                raise OSError('private-upstream-token')

            monkeypatch.setattr(session, '_open_transport', failed)
            session.start_interrupt()
            await session.listen(True)
            await session.audio(bytes(1920))
            await eventually(lambda: session.state == 'error')
            assert session.pending_input is None and session.cloud is None
            assert 'private-upstream-token' not in str(messages)
        finally:
            await session.disconnect()
            await session.motion.close()


async def test_interrupt_without_microphone_returns_ready_without_auto_recording(tmp_path):
    async def cloud(ws):
        await handshake(ws)
        async for message in ws:
            assert json.loads(message)['type'] == 'abort'

    async with serve(cloud, '127.0.0.1', 0) as server:
        session, _ = session_for(tmp_path, server.sockets[0].getsockname()[1])
        try:
            await session.open()
            session.start_interrupt()
            await eventually(lambda: session.state == 'ready' and session.pending_input is None)
            assert session.turn == 0
        finally:
            await session.disconnect()
            await session.motion.close()

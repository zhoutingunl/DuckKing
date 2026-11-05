import asyncio
import json
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app
from duckking.config import Settings
from duckking.diagnostics import VoiceDiagnostics
from duckking.motion import Action


def endpoint(app, path):
    return next(route.endpoint for route in app.routes if route.path == path)


def test_old_service_requests_cannot_replay_actions_or_acquire_voice(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        instance = client.get('/api/rooms').json()['instance']
        assert len(instance) == 32
        rejected = client.post('/api/actions?server_instance=old-process', json={'name': 'walk'})
        assert rejected.status_code == 409 and rejected.json()['code'] == 'room_expired'
        assert app.state.motion.current is None
        with client.websocket_connect('/voice?room=1&server_instance=old-process') as ws:
            assert ws.receive_json()['type'] == 'room_expired'
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1008
        assert app.state.voice is None
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type': 'join_room', 'room': '1', 'server_instance': 'old-process'})
            assert ws.receive_json()['type'] == 'room_expired'
        assert client.post(f'/api/actions?server_instance={instance}',
                           json={'name': 'stop'}).status_code == 202


async def test_visible_room_heartbeat_and_pending_preparation_prevent_reaping(
    tmp_path, direct_room_visitor
):
    app = create_app(settings=Settings(data_dir=tmp_path, max_rooms=3, room_idle_seconds=30))
    registry = app.state.room_registry
    number = (await registry.claim(create=True, owner=direct_room_visitor))['room']
    room = registry.get(number)
    room.reserved_until = 0
    room.last_used = 0
    await endpoint(app, '/api/rooms')(room=number)
    assert room.last_used > 0
    room.last_used = 0
    await app.state.physics_lock.acquire()
    task = asyncio.create_task(endpoint(app, '/api/scenes/start')(
        Action(name='scene_ball'), room=number))
    try:
        await asyncio.sleep(0)
        room.last_used = 0
        assert room.preparing['phase'] == 'waiting'
        await registry.reap()
        assert number in registry.rooms
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert room.preparing is None
    finally:
        app.state.physics_lock.release()
    await registry.reap()
    assert number not in registry.rooms


async def test_cancelled_build_retains_admission_and_disposes_late_world(
    tmp_path, monkeypatch, direct_room_visitor
):
    app = create_app(settings=Settings(data_dir=tmp_path))
    started, release = threading.Event(), threading.Event()
    closed = []

    class Backend:
        def __init__(self, assets, *, progress):
            progress('models', 1, 3)
            started.set()
            assert release.wait(5)

        async def close(self):
            closed.append(True)

    monkeypatch.setattr('duckking.simulation.MuJoCoBackend', Backend)
    task = asyncio.create_task(endpoint(app, '/api/scenes/start')(Action(name='scene_ball'), '1'))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(.01)
        assert app.state.physics_lock.locked() and app.state.preparing is not None
        assert not closed
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True]
    assert app.state.scene_motion is None and app.state.preparing is None
    assert not app.state.physics_lock.locked()


async def test_native_failure_clears_progress_without_preview_fallback(
    tmp_path, monkeypatch, direct_room_visitor
):
    app = create_app(settings=Settings(data_dir=tmp_path))

    def fail(*args, **kwargs):
        raise RuntimeError('private backend failure')

    monkeypatch.setattr('duckking.simulation.MuJoCoBackend', fail)
    with pytest.raises(HTTPException) as error:
        await endpoint(app, '/api/scenes/start')(Action(name='scene_ball'), '1')
    assert error.value.status_code == 503 and 'private' not in error.value.detail
    assert app.state.scene_motion is None and app.state.preparing is None


def test_statistics_restore_redacted_rounds_without_replaying_or_rewriting(tmp_path):
    path = tmp_path / 'voice.jsonl'
    one = VoiceDiagnostics(path)
    fields = {'turn': one.next_turn(), 'backend': 'preview'}
    for event, elapsed, extra in [
        ('listen_start', 0, {}), ('listen_stop', 100, {}),
        ('stt', 200, {'text': '点头 token=secret-value'}),
        ('tts_stop', 500, {'result': 'ok'}),
    ]:
        one.record(event, **fields, elapsed_ms=elapsed, **extra)
    original = path.read_bytes()

    class Experience:
        def observe(self, *args):
            pytest.fail('Historical diagnostics must not be submitted as fresh experience')

    two = VoiceDiagnostics(path, experience=Experience())
    assert path.read_bytes() == original
    snapshot = two.statistics.snapshot()
    assert snapshot['rounds'][0]['text'] == '' and snapshot['rounds'][0]['historical']
    assert snapshot['restored_rounds'] == 1 and snapshot['counts']['replied'] == 1
    assert snapshot['latencies']['stt']['p50_ms'] == 100
    assert 'secret-value' not in json.dumps(snapshot)
    assert two.next_turn() > fields['turn']
    two.experience = None
    pending = {'turn': two.turn_sequence, 'backend': 'mujoco'}
    two.record('listen_start', **pending, elapsed_ms=0)
    two.record('listen_stop', **pending, elapsed_ms=100)
    two.record('action_start', **pending, elapsed_ms=200, call=7, tool='duck_nod')
    restored = VoiceDiagnostics(path).statistics.snapshot()
    row = restored['rounds'][0]
    assert row['status'] == 'interrupted' and row['reason'] == 'service_restart'
    assert row['actions'][0]['result'] == 'cancelled'
    assert row['actions'][0]['duration_ms'] is None
    assert restored['counts']['pending'] == 0


def test_journal_recovery_separates_reused_turn_ids_and_rejects_extra_fields(tmp_path):
    path = tmp_path / 'voice.jsonl'
    events = []
    for epoch in range(2):
        for ident, event, elapsed, extra in [
            (1, 'listen_start', 0, {}), (2, 'listen_stop', 100, {}),
            (3, 'stt', 200, {'text': 'hello token=fake-token 00:11:22:33:44:55'}),
            (4, 'tts_stop', 400, {'result': 'ok'}),
        ]:
            events.append({'id': ident, 'event': event, 'turn': 1, 'backend': 'preview',
                           'time': f'2026-11-03T0{epoch}:00:00+00:00', 'elapsed_ms': elapsed,
                           'credential': 'must-not-survive', **extra})
    path.write_text('corrupt\n' + '\n'.join(json.dumps(row) for row in events))
    journal = VoiceDiagnostics(path)
    payload = journal.statistics.snapshot()
    assert payload['counts']['replied'] == 2
    assert len({r['turn'] for r in payload['rounds']}) == 2
    assert payload['history_incomplete'] is True
    assert 'must-not-survive' not in str(journal.snapshot())
    assert 'fake-token' not in str(payload) and '00:11:22:33:44:55' not in str(payload)


def test_recovery_does_not_cross_processes_or_invent_durations(tmp_path, monkeypatch):
    path = tmp_path / 'voice.jsonl'
    events = []
    for epoch, sequence in enumerate([
        [('listen_start', None), ('state', 'recovering')],
        [('listen_start', None), ('state', 'ready'), ('state', 'recovering'), ('state', 'ready')],
    ]):
        for index, (event, state) in enumerate(sequence, 1):
            events.append({'id': index, 'event': event, 'state': state, 'turn': 1,
                           'backend': 'preview', 'elapsed_ms': index * 100,
                           'time': f'2026-11-03T0{epoch}:00:0{index}+00:00'})
    path.write_text('\n'.join(json.dumps(e) for e in events))
    journal = VoiceDiagnostics(path)
    restored = journal.statistics.snapshot()
    assert restored['service']['reconnect_attempts'] == 2
    assert restored['service']['reconnect_successes'] == 1
    assert restored['latencies']['recovery']['count'] == 0
    clock = iter([1.0, 1.25])
    monkeypatch.setattr('duckking.diagnostics.time.monotonic', lambda: next(clock))
    journal.record('state', backend='preview', state='recovering')
    journal.record('state', backend='preview', state='ready')
    assert journal.statistics.snapshot()['latencies']['recovery']['p50_ms'] == 250

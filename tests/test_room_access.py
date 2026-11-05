import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app
from duckking.config import Settings
from duckking.experience import ExperienceEvent, ExperienceStore
from duckking.room_access import COOKIE_NAME

pytestmark = pytest.mark.anonymous_rooms


@contextmanager
def visitors(tmp_path, **settings):
    app = create_app(settings=Settings(data_dir=tmp_path, **settings))
    with TestClient(app) as first:
        second = TestClient(app)
        # Two independent cookie jars use one application's lifespan/event loop.
        second.portal = first.portal
        try:
            yield app, first, second
        finally:
            second.close()
            second.portal = None


def sample(ident=None, value=111, sequence=1):
    return {"events": [{"id": ident or str(uuid.uuid4()), "sequence": sequence,
                        "kind": "voice", "status": "completed",
                        "metrics": {"reply_ms": value}}]}


def test_visitors_only_list_and_control_their_own_rooms(tmp_path):
    with visitors(tmp_path) as (app, first, second):
        assert first.get('/api/state?room=1').status_code == 404
        assert first.get('/api/rooms').json()['rooms'] == []
        a = first.post('/api/rooms/claim').json()['room']
        b = second.post('/api/rooms/claim').json()['room']
        assert a != b
        assert [r['id'] for r in first.get('/api/rooms').json()['rooms']] == [a]
        assert [r['id'] for r in second.get('/api/rooms').json()['rooms']] == [b]
        public = first.get('/api/rooms').text
        assert first.cookies.get(COOKIE_NAME) not in public
        assert '"owner"' not in public and '"lease"' not in public
        action = first.post(f'/api/actions?room={a}', json={"name": "walk", "duration": 3})
        ident = action.json()['id']
        previous_touch = app.state.rooms[a].last_used
        paths = ["api/state", "api/scenes/state", "api/scenes/model.dkm.gz",
                 "api/voice/diagnostics", "api/voice/statistics", "api/voice/profiles",
                 f"api/actions/{ident}", "api/experience"]
        for path in paths:
            assert second.get(f'/{path}?room={a}').status_code == 404
        for path, body in [
            ('api/actions', {"name": "stop"}),
            ('api/scenes/start', {"name": "scene_ball"}),
            ('api/scenes/close', None),
            ('api/balance/prepare', {}),
            ('api/seesaw/prepare', {}),
            ('api/experience', sample()),
        ]:
            assert second.post(f'/{path}?room={a}', json=body).status_code == 404
        assert app.state.rooms[a].last_used == previous_touch
        assert second.get(f'/api/state?room={a}').json() == second.get(
            '/api/state?room=99').json()
        assert first.get(f'/api/actions/{ident}?room={a}').json()['status'] != 'cancelled'
        assert first.post(f'/api/actions?room={a}', json={"name": "stop"}).status_code == 202
        assert app.state.rooms[a].scene_motion is None
        assert app.state.rooms[b].scene_motion is None


@pytest.mark.parametrize('endpoint', ['ws', 'scene-ws', 'voice', 'scene-voice'])
def test_all_sockets_reject_a_different_visitor_before_sending_state(tmp_path, endpoint):
    with visitors(tmp_path) as (app, first, second):
        room = first.post('/api/rooms/claim').json()['room']
        second.get('/api/rooms')
        with second.websocket_connect(f'/{endpoint}?room={room}') as socket:
            assert socket.receive_json() == {"type": "room_expired", "reason": "unavailable"}
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1008
        assert app.state.rooms[room].voice is None
        assert app.state.rooms[room].viewers == 0
        with second.websocket_connect(f'/{endpoint}?room=99') as socket:
            assert socket.receive_json() == {"type": "room_expired", "reason": "unavailable"}
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
        second.cookies.clear()
        with pytest.raises(WebSocketDisconnect):
            with second.websocket_connect(f'/{endpoint}?room={room}'):
                pass


def test_signed_http_only_session_cannot_be_forged(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path), allowed_hosts=['duck.qbox.net'])
    with TestClient(app, base_url='https://duck.qbox.net') as client:
        response = client.post('/api/rooms/claim')
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
        assert response.headers['cache-control'] == 'no-store'
        assert 'Cookie' in response.headers['vary']
        token = client.cookies.get(COOKIE_NAME)
        assert token not in json.dumps(response.json())
        room = response.json()['room']
        assert client.get(f'/api/state?room={room}').status_code == 200
        client.cookies.clear()
        forged = ('a' if token[0] != 'a' else 'b') + token[1:]
        client.cookies.set(COOKIE_NAME, forged)
        assert client.get(f'/api/state?room={room}').status_code == 404
        assert client.get('/api/rooms').json()['rooms'] == []


@pytest.mark.parametrize('cookie', ['', 'unknown-session', 'a' * 76, 'x' * 300])
def test_malformed_session_does_not_grant_an_existing_room(tmp_path, cookie):
    with visitors(tmp_path) as (_, first, second):
        room = first.post('/api/rooms/claim').json()['room']
        second.cookies.set(COOKIE_NAME, cookie)
        assert second.get(f'/api/state?room={room}').status_code == 404
        assert second.get('/api/rooms').json()['rooms'] == []
        assert first.get(f'/api/state?room={room}').status_code == 200


def test_idle_voice_pool_keeps_its_visitor_until_reclaimed(tmp_path):
    with visitors(tmp_path, max_rooms=2, english_rooms=('2',)) as (app, first, second):
        assert first.post('/api/rooms/claim?language=en').json() == {
            'room': '2', 'voice_language': 'en'}
        app.state.rooms['2'].reserved_until = 0
        assert second.post('/api/rooms/claim?language=en').json() == {
            'room': '1', 'voice_language': 'default'}
        assert [r['id'] for r in first.get('/api/rooms').json()['rooms']] == ['2']
        assert [r['id'] for r in second.get('/api/rooms').json()['rooms']] == ['1']
        assert second.post('/api/rooms').status_code == 409


def test_metrics_and_reclaimed_numeric_slots_do_not_leak_previous_visitors(tmp_path):
    with visitors(tmp_path, room_idle_seconds=30) as (app, first, second):
        room = first.post('/api/rooms/claim').json()['room']
        payload = sample()
        assert first.post(f'/api/experience?room={room}', json=payload).status_code == 202
        action = first.post(f'/api/actions?room={room}', json={'name': 'nod', 'duration': .2})
        old_id = action.json()['id']
        first.portal.call(app.state.rooms[room].motion.wait, old_id)
        app.state.rooms[room].voice_diagnostics.record('stt', text='previous visitor', turn=1)
        app.state.experience.flush()
        assert first.get('/api/experience?traffic=all').json()['samples'] == 1
        assert second.get('/api/experience?traffic=all').json()['samples'] == 0
        old = app.state.rooms[room]
        old.last_used = time.monotonic() - 31
        old.reserved_until = 0
        first.portal.call(app.state.room_registry.reap)
        assert second.post('/api/rooms/claim').json()['room'] == room
        assert first.get(f'/api/state?room={room}').status_code == 404
        assert second.get(f'/api/actions/{old_id}?room={room}').status_code == 404
        assert 'previous visitor' not in second.get(f'/api/voice/diagnostics?room={room}').text
        assert second.get('/api/experience?traffic=all').json()['samples'] == 0
        # A chosen UUID cannot overwrite a previous lease's technical sample.
        forged = sample(payload['events'][0]['id'], value=999, sequence=2)
        assert second.post(f'/api/experience?room={room}', json=forged).status_code == 202
        app.state.experience.flush()
        stored = app.state.experience.snapshot(traffic='all')
        assert stored['samples'] == 1 and stored['groups'][0]['mean_ms'] == 111


def test_concurrent_http_claims_do_not_share_request_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    with visitors(tmp_path) as (_, first, second):
        first.get('/api/rooms')
        second.get('/api/rooms')
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda client: client.post('/api/rooms/claim').json()['room'],
                                   (first, second)))
        assert len(set(claims)) == 2
        for client, room in zip((first, second), claims, strict=True):
            assert [r['id'] for r in client.get('/api/rooms').json()['rooms']] == [room]


def test_legacy_metrics_migrate_without_joining_a_new_room_lease(tmp_path):
    path = tmp_path / 'experience.sqlite3'
    legacy = ExperienceStore(path)
    legacy.submit(ExperienceEvent.model_validate(sample()['events'][0]), source='browser', room='1')
    legacy.flush()
    legacy.close()
    # Recreate the pre-ownership schema without using a version-specific DROP COLUMN.
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(samples)') if row[1] != 'scope']
        db.execute('CREATE TABLE legacy_samples AS SELECT '+','.join(columns)+' FROM samples')
        db.execute('DROP TABLE samples')
        db.execute('ALTER TABLE legacy_samples RENAME TO samples')
        db.execute('CREATE UNIQUE INDEX legacy_sample_key ON samples(id,source)')
    current = ExperienceStore(path)
    try:
        assert current.snapshot(scopes=('new-room-lease',), traffic='all')['samples'] == 0
        assert current.storage_ok
        current.submit(ExperienceEvent.model_validate(sample()['events'][0]), source='browser',
                       room='1', scope='new-room-lease')
        current.flush()
        assert current.storage_ok and current.dropped == 0
        assert current.snapshot(scopes=('new-room-lease',), traffic='all')['samples'] == 1
        assert current.snapshot(scopes=(), traffic='all')['samples'] == 0
        assert current.snapshot(traffic='all')['samples'] == 2
    finally:
        current.close()


import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app
from duckking.config import Settings
from duckking.motion import MotionController
from duckking.robotd import RobotdBackend


def join(client, room, endpoint="ws"):
    return client.websocket_connect(f"/{endpoint}?room={room}")


def test_rooms_allocate_atomically_and_release_viewers(tmp_path):
    with TestClient(create_app(settings=Settings(data_dir=tmp_path, max_rooms=2))) as client:
        assert client.post('/api/rooms/claim').json() == {"room": "1"}
        assert client.post('/api/rooms/claim').json() == {"room": "2"}
        assert client.post('/api/rooms/claim').status_code == 409
        with join(client, "1") as ws:
            assert ws.receive_json()['type'] == 'state'
            assert client.get('/api/rooms').json()['rooms'][0]['viewers'] == 1
        assert client.post('/api/rooms/claim').json() == {"room": "1"}


def test_room_actions_and_voice_ownership_are_separate(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        with join(client, "1", "voice") as first, join(client, "2", "voice") as second:
            assert first.receive_json()['state'] == second.receive_json()['state'] == 'disconnected'
            with join(client, "2", "voice") as duplicate:
                assert duplicate.receive_json()['state'] == 'busy'
            client.post('/api/actions?room=1', json={"name": "walk", "duration": 3,
                                                   "request_id": "same-local-id"})
            client.post('/api/actions?room=2', json={"name": "turn_left", "duration": 3,
                                                   "request_id": "same-local-id"})
            first.send_json({"type": "disconnect"})
            assert first.receive_json()['state'] == 'disconnected'
            assert app.state.rooms['2'].voice is not None
            client.post('/api/actions?room=1', json={"name": "stop"})
            assert client.get('/api/actions/same-local-id?room=1').json()['status'] == 'cancelled'
            assert client.get('/api/actions/same-local-id?room=2').json()['status'] == 'running'
            assert client.get('/api/state?room=2').json()['action']['name'] == 'turn_left'
            second.send_json({"type": "ping"})
            assert second.receive_json() == {"type": "pong"}
        assert client.get('/api/state?room=3').status_code == 404
        assert client.get('/api/actions/missing?room=2').status_code == 404


def test_first_protocol_frame_selects_room_through_unchanged_gateway(tmp_path):
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with client.websocket_connect('/voice') as ws:
            ws.send_json({"type": "join_room", "room": "2"})
            assert ws.receive_json()['state'] == 'disconnected'
            assert client.get('/api/rooms').json()['rooms'][1]['voice_busy']
        for data in [{"type": "connect"}, {"type": "join_room", "room": []},
                     {"type": "join_room", "room": "3"}, []]:
            with client.websocket_connect('/voice') as ws:
                ws.send_json(data)
                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()


def test_independent_identities_and_diagnostics_without_exposing_device_data(tmp_path):
    settings = Settings(data_dir=tmp_path, ws_token='first-private-token')
    second = settings.for_room('2')
    assert second.ws_token == second.device_id == second.client_id == ''
    one_id, two_id = settings.identity(), second.identity()
    assert one_id['device_id'] != two_id['device_id']
    assert one_id['client_id'] != two_id['client_id']
    assert second.identity() == two_id
    assert settings.for_room('1') is settings
    with pytest.raises(ValueError):
        settings.for_room('11')
    (second.data_dir / 'linx.env').write_text('LINX_WS_TOKEN=second-private-token\n')
    assert settings.for_room('2').ws_token == 'second-private-token'
    app = create_app(settings=settings)
    with TestClient(app) as client:
        app.state.voice_diagnostics.record('stt', text='房间一的命令', turn=1)
        app.state.rooms['2'].voice_diagnostics.record('stt', text='房间二的命令', turn=1)
        first = client.get('/api/voice/diagnostics?room=1').text
        second = client.get('/api/voice/diagnostics?room=2').text
        assert '房间二' not in first and '房间一' not in second
        for value in [*one_id.values(), *two_id.values(), 'private-token']:
            assert value not in first + second + client.get('/api/rooms').text
        assert client.get('/api/voice/statistics?room=2').status_code == 200


def test_robotd_does_not_silently_create_a_preview_room(tmp_path):
    app = create_app(MotionController(RobotdBackend('/tmp/no-room-robot.sock')),
                     settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        assert len(client.get('/api/rooms').json()['rooms']) == 1
        assert client.get('/api/state?room=2').status_code == 404


def test_mujoco_worlds_and_scene_actions_are_isolated(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        for number, name in [('1', 'scene_ball'), ('2', 'scene_duo')]:
            r = client.post(f'/api/scenes/start?room={number}', json={'name': name})
            assert r.status_code == 202
            client.portal.call(app.state.rooms[number].scene_motion.wait, r.json()['id'])
        one = client.get('/api/scenes/state?room=1').json()
        two = client.get('/api/scenes/state?room=2').json()
        assert one['backend']['scene'] == 'ball' and two['backend']['scene'] == 'duo'
        assert one['backend']['revision'] != two['backend']['revision']
        with client.websocket_connect('/scene-ws') as ws:
            ws.send_json({'type': 'join_room', 'room': '2'})
            assert ws.receive_json()['backend']['scene'] == 'duo'
        assert (app.state.scene_motion.backend.data
                is not app.state.rooms['2'].scene_motion.backend.data)
        assert client.get('/api/scenes/model?room=2').status_code == 200
        r = client.post('/api/scenes/actions?room=2', json={'name': 'stop'})
        assert r.status_code == 202
        assert client.get('/api/scenes/actions/'+r.json()['id']+'?room=1').status_code == 404
        assert client.get('/api/scenes/actions/'+r.json()['id']+'?room=2').status_code == 200


def test_prefixed_scene_voice_uses_selected_room_scene_controller(tmp_path):
    from duckking.motion import PreviewBackend

    app = create_app(settings=Settings(data_dir=tmp_path))
    scene = MotionController(PreviewBackend())
    app.state.rooms['2'].scene_motion = scene
    with TestClient(app, root_path='/duckking') as client:
        with client.websocket_connect('/scene-voice?room=2') as ws:
            assert ws.receive_json()['state'] == 'disconnected'
            assert app.state.rooms['2'].voice.motion is scene
            assert app.state.voice is None


def test_browser_audio_reports_stay_in_owner_room_and_survive_disconnect(tmp_path):
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with join(client, '1', 'voice') as ws:
            assert ws.receive_json()['state'] == 'disconnected'
            ws.send_json({'type': 'playback_status', 'output_state': []})
            assert ws.receive_json()['type'] == 'error'
            ws.send_json({'type': 'playback_status', 'output_state': 'interrupted',
                          'received_frames': 42, 'token': 'private-secret'})
            ws.send_json({'type': 'ping'})
            assert ws.receive_json() == {'type': 'pong'}
            first = client.get('/api/voice/diagnostics?room=1').json()
            assert first['browser_audio']['received_frames'] == 42
            assert client.get('/api/voice/diagnostics?room=2').json()['browser_audio'] is None
            with join(client, '1', 'voice') as duplicate:
                assert duplicate.receive_json()['state'] == 'busy'
            assert 'private-secret' not in str(first)
            ws.send_json({'type': 'disconnect'})
            assert ws.receive_json()['state'] == 'disconnected'
        assert client.get('/api/voice/diagnostics?room=1').json()['browser_audio'] == {
            'output_state': 'interrupted', 'received_frames': 42,
        }
        with join(client, '1', 'voice') as next_browser:
            assert next_browser.receive_json()['state'] == 'disconnected'
            assert client.get('/api/voice/diagnostics?room=1').json()['browser_audio'] is None


def test_dynamic_room_claims_are_bounded_and_concurrent(tmp_path):
    import asyncio

    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        async def claims():
            return await asyncio.gather(*(app.state.room_registry.claim() for _ in range(12)),
                                        return_exceptions=True)
        results = client.portal.call(claims)
        assert {r['room'] for r in results if isinstance(r, dict)} == {str(i) for i in range(1, 11)}
        assert sum(getattr(r, 'status_code', None) == 409 for r in results) == 2
        assert client.post('/api/rooms').status_code == 409
        data = client.get('/api/rooms').json()
        assert data['capacity'] == 10 and len(data['rooms']) == 10
        assert data['physics_active'] == 0 and data['physics_capacity'] == 4
        with join(client, '10') as ws:
            assert ws.receive_json()['type'] == 'state'
        assert client.post('/api/rooms/claim').json() == {'room': '10'}
        denied = client.post('/api/rooms', headers={'Origin': 'https://elsewhere.invalid'})
        assert denied.status_code == 403


def test_dynamic_rooms_keep_ten_voice_owners_and_device_identities_separate(tmp_path):
    from contextlib import ExitStack

    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client, ExitStack() as stack:
        for _ in range(8):
            assert client.post('/api/rooms').status_code == 201
        identities = [room.settings.identity() for room in app.state.rooms.values()]
        assert len({identity['device_id'] for identity in identities}) == 10
        assert len({identity['client_id'] for identity in identities}) == 10
        sockets = [stack.enter_context(join(client, str(i), 'voice')) for i in range(1, 11)]
        assert all(ws.receive_json()['state'] == 'disconnected' for ws in sockets)
        sockets[0].send_json({'type': 'disconnect'})
        assert sockets[0].receive_json()['state'] == 'disconnected'
        for ws in sockets[1:]:
            ws.send_json({'type': 'ping'})
            assert ws.receive_json() == {'type': 'pong'}
        public = client.get('/api/rooms').text
        assert all(value not in public for identity in identities for value in identity.values())
        assert sum(r['voice_busy'] for r in client.get('/api/rooms').json()['rooms']) == 9


def test_idle_reaping_preserves_viewers_voice_and_actions_and_closes_worlds(tmp_path):
    from duckking.motion import PreviewBackend

    app = create_app(settings=Settings(data_dir=tmp_path, room_idle_seconds=30))
    with TestClient(app) as client:
        for _ in range(3):
            assert client.post('/api/rooms').status_code == 201
        registry = app.state.room_registry
        for room in app.state.rooms.values():
            room.last_used -= 31
            room.reserved_until = 0
        # A viewer and a reserved voice must both prevent reclamation.
        with join(client, '3') as viewer, join(client, '4', 'voice') as voice:
            viewer.receive_json()
            voice.receive_json()
            for room in (app.state.rooms['3'], app.state.rooms['4']):
                room.last_used -= 31
            idle = app.state.rooms['5']
            idle.scene_motion = MotionController(PreviewBackend())
            closed = []
            original_close = idle.scene_motion.close
            async def observed_close():
                closed.append(True)
                await original_close()
            idle.scene_motion.close = observed_close
            client.portal.call(registry.reap)
            assert {'3', '4'} <= app.state.rooms.keys()
            assert '5' not in app.state.rooms and closed == [True]
        # Closing a viewer updates last_used, so it is not immediately recycled.
        client.portal.call(registry.reap)
        assert '3' in app.state.rooms
        action = client.post('/api/actions?room=3', json={'name': 'walk', 'duration': 3}).json()
        app.state.rooms['3'].last_used -= 31
        client.portal.call(registry.reap)
        assert '3' in app.state.rooms
        client.post('/api/actions?room=3', json={'name': 'stop'})
        assert client.get('/api/actions/'+action['id']+'?room=3').json()['status'] == 'cancelled'
        app.state.rooms['3'].last_used -= 31
        client.portal.call(registry.reap)
        assert client.get('/api/state?room=3').status_code == 404
        assert client.post('/api/rooms').json() == {'room': '3'}
        assert client.get('/api/voice/statistics?room=3').json()['counts']['rounds'] == 0


def test_physics_capacity_is_released_without_changing_another_room(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path, max_physics_rooms=1))
    with TestClient(app) as client:
        start = client.post('/api/scenes/start?room=1', json={'name': 'scene_ball'})
        assert start.status_code == 202
        client.portal.call(app.state.scene_motion.wait, start.json()['id'])
        denied = client.post('/api/scenes/start?room=2', json={'name': 'scene_ball'})
        assert denied.status_code == 409 and '上限' in denied.json()['detail']
        assert client.get('/api/scenes/state?room=2').status_code == 503
        assert client.post('/api/actions?room=2', json={'name': 'nod'}).status_code == 202
        with join(client, '1', 'scene-voice') as ws:
            ws.receive_json()
            assert client.post('/api/scenes/close?room=1').status_code == 409
        assert client.post('/api/scenes/close?room=1').status_code == 204
        assert client.get('/api/scenes/state?room=1').status_code == 503
        started = client.post('/api/scenes/start?room=2', json={'name': 'scene_duo'})
        assert started.status_code == 202
        assert client.get('/api/rooms').json()['physics_active'] == 1


def test_room_settings_reject_invalid_paths_and_limits(tmp_path):
    settings = Settings(data_dir=tmp_path)
    for bad in ['../secret', '0', '01', '-1', '', '11', [], None]:
        with pytest.raises(ValueError):
            settings.for_room(bad)
    for kwargs in [{'max_rooms': 0}, {'max_rooms': 33}, {'max_physics_rooms': 0},
                   {'room_idle_seconds': 0}]:
        with pytest.raises(ValueError):
            Settings(**kwargs)

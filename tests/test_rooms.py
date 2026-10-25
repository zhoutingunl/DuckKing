
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
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
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
        settings.for_room('3')
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

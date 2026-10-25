import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.config import Settings
from duckking.mcp import DeviceMCP
from duckking.motion import Action, MotionController, PreviewBackend
from duckking.studio import Studio
from duckking.studio_tasks import load_recipes, save_recipes
from duckking.voice import VoiceSession
from duckking.voice_profiles import profiles, store_profiles

ASSETS = Path(__file__).resolve().parents[1] / 'external'


@pytest.fixture
async def studio(tmp_path):
    motion = MotionController(PreviewBackend())
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    yield studio
    await motion.close()


async def test_cancel_before_first_tick_never_runs_old_task(studio):
    await studio.select('director')
    first = await studio.start('director', lambda: studio.move('walk'))
    await studio.external(Action(name='stop'))
    result = await studio.wait(first)
    assert result['operation_failed']
    assert result['task']['status'] == 'cancelled'
    assert not any(r['name'] == 'walk' for r in studio.motion.records.values())


async def test_cancel_tool_reports_success_after_failed_plan(studio):
    await studio.select('director')
    await studio.invoke('duck_direct', {'title': 'needs physics', 'steps': [{'action': 'sit'}]})
    mcp = DeviceMCP(studio.motion, 'failure')
    try:
        response = await mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'duck_task', 'arguments': {'operation': 'cancel'}}})
        assert not response['result']['isError']
        listing = await mcp.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        names = {t['name'] for t in listing['result']['tools']}
        assert 'duck_direct' in names and 'duck_delivery' not in names
        bypass = await mcp.handle({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
            'params': {'name': 'duck_walk', 'arguments': {'duration': .2}}})
        assert bypass['result']['isError']
        assert not any(r['name'] == 'walk' for r in studio.motion.records.values())
        bad = await mcp.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                               'params': {'name': []}})
        assert bad['result']['isError']
    finally:
        await mcp.close()


@pytest.mark.parametrize('command', [
    {'operation': 'draft', 'name': 'missing'},
    {'operation': 'confirm', 'name': 'missing'},
    {'operation': 'run', 'name': 'missing'},
    {'operation': 'delete', 'name': 'missing'},
])
async def test_invalid_recipe_operations_never_start_actions(studio, command):
    await studio.select('recipe')
    with pytest.raises(ValueError):
        await studio.invoke('duck_recipe', command)
    assert not studio.motion.records


def test_recipe_persistence_rejects_corrupt_and_unsafe_programs(tmp_path):
    path = tmp_path / 'recipes.json'
    assert load_recipes(path) == {}
    for data in [[],
                 {'bad': {'plan': {'title': 'x', 'steps': [{'action': 'shell'}]}, 'version': 1}},
                 {'bad': {'plan': {'title': 'x', 'steps': [{'action': 'nod'}]}, 'version': 0}}]:
        save_recipes(path, data)
        with pytest.raises(ValueError):
            load_recipes(path)
    assert path.stat().st_mode & 0o777 == 0o600


async def test_recipe_capacity_and_manual_confirmation(studio):
    await studio.select('recipe')
    plan = {'title': '点头', 'steps': [{'action': 'nod', 'duration': .2}]}
    studio.helpers.recipes = {f'动作{i}': {'version': 1, 'plan': plan} for i in range(20)}
    with pytest.raises(ValueError, match='20'):
        await studio.invoke('duck_recipe', {'operation': 'draft', 'name': '新名字', 'plan': plan})
    await studio.invoke('duck_recipe', {'operation': 'draft', 'name': '动作0', 'plan': plan})
    await studio.invoke('duck_recipe', {'operation': 'confirm', 'name': '动作0'}, manual=True)
    assert studio.helpers.recipes['动作0']['version'] == 2
    assert len((await studio.invoke('duck_recipe', {'operation': 'list'}))['recipes']) == 20


async def test_game_not_configured_missing_plan_and_explicit_exit(studio):
    await studio.select('game')
    with pytest.raises(ValueError, match='口令'):
        await studio.invoke('duck_game', {'operation': 'play'})
    await studio.invoke('duck_game', {'operation': 'configure', 'prefix': '船长说'})
    studio.heard('船长说，点头')
    with pytest.raises(ValueError, match='计划'):
        await studio.invoke('duck_game', {'operation': 'play'})
    with pytest.raises(ValueError, match='规则'):
        await studio.motion.submit(Action(name='nod'))
    assert (await studio.invoke('duck_game', {'operation': 'status'}))['game']['prefix'] == '船长说'
    await studio.invoke('duck_game', {'operation': 'stop'})
    assert studio.helpers.prefix is None
    await studio.external(Action(name='reset'))
    assert studio.active is None and not studio.tools()


async def test_timer_fires_once_and_late_extension_is_rejected(studio):
    await studio.select('focus')
    moves, announcements = [], []
    async def move(name, **kwargs):
        moves.append(name)
        return {'name': name, 'status': 'completed'}
    async def announce(text):
        announcements.append(text)
    studio.move, studio.announce = move, announce
    with pytest.raises(ValueError):
        await studio.invoke('duck_focus', {'operation': 'extend', 'seconds': 5})
    await studio.invoke('duck_focus', {'operation': 'start', 'seconds': 5})
    await asyncio.sleep(.01)
    studio.helpers.deadline = time.monotonic() + .03
    studio.helpers.timer_event.set()
    await asyncio.wait_for(studio.task, 2)
    assert moves.count('stand') == 1 and len(announcements) == 1
    assert (await studio.invoke('duck_focus', {'operation': 'status'}))['focus_remaining_s'] is None
    with pytest.raises(ValueError):
        await studio.invoke('duck_focus', {'operation': 'extend', 'seconds': 5})


async def test_unknown_or_wrong_scene_tools_have_no_side_effect(studio):
    with pytest.raises(ValueError):
        await studio.select('unknown')
    with pytest.raises(ValueError):
        await studio.invoke('duck_direct', {})
    await studio.select('director')
    for name, args in [('unknown', {}), ([], {}), ('duck_coach', {'operation': 'observe'}),
                       ('duck_delivery', {'operation': 'status'}),
                       ('duck_conduct', {'operation': 'status'}),
                       ('duck_focus', {'operation': 'status'})]:
        with pytest.raises(ValueError):
            await studio.invoke(name, args)
    assert not studio.motion.records


def test_studio_api_rejects_wrong_world_and_voice_ownership(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        assert client.get('/api/studio').status_code == 503
        assert client.post('/api/studio/select', json={'scene': []}).status_code == 422
        client.post('/api/scenes/start', json={'name': 'scene_ball'})
        assert client.post('/api/studio/select', json={'scene': 'delivery'}).status_code == 409
        assert client.post('/api/studio/select', json={'scene': 'director'}).status_code == 200
        assert client.get('/api/studio').json()['scene'] == 'director'
        assert client.post('/api/studio/action', json={'name': []}).status_code == 422
        with client.websocket_connect('/scene-voice?room=1') as ws:
            ws.receive_json()
            assert client.post('/api/studio/select', json={'scene': 'director'}).status_code == 409
            ws.send_json({'type': 'connect', 'mode': 'local_first'})
            assert '灵矽' in ws.receive_json()['message']


def test_invalid_private_profiles_are_rejected(tmp_path):
    settings = Settings(data_dir=tmp_path)
    assert profiles(settings) == {'voices': {}, 'agents': {}}
    path = tmp_path / 'voice-profiles.json'
    for data in [{'voices': []}, {'voices': {'bad': {'id': '\r\nprivate'}}}]:
        store_profiles(path, data)
        with pytest.raises(ValueError):
            profiles(settings)


async def test_announcements_mark_origin_and_require_idle_cloud(studio, tmp_path):
    messages, frames = [], []
    async def send(data):
        messages.append(data)
    async def cloud(data):
        frames.append(data)
    session = VoiceSession(send, studio.motion, Settings(
        data_dir=tmp_path, ws_url='ws://127.0.0.1:1', ws_token='fixture'))
    await session.announce('时间到了')
    assert messages[-1]['spoken'] is False and not frames
    session.cloud = object()
    session.state = 'ready'
    session._json = cloud
    await session.announce('时间到了')
    assert frames[-1]['type'] == 'listen' and frames[-1]['state'] == 'detect'
    assert '时间到了' in frames[-1]['text']
    assert session.state == 'thinking'
    session.cloud = None
    with pytest.raises(ValueError):
        session.set_persona({'persona': 'coach'})
    session.persona = 'coach'
    await session.open()
    assert session.state == 'error'  # No configured/bound remote device for this fixture.
    await session.disconnect()


async def test_busy_announcement_waits_and_cancellation_prevents_late_speech(
    studio, tmp_path, monkeypatch,
):
    messages, frames = [], []
    async def send(data):
        messages.append(data)
    async def cloud(data):
        frames.append(data)
    session = VoiceSession(send, studio.motion, Settings(data_dir=tmp_path))
    session.cloud, session.state, session._json = object(), 'speaking', cloud
    pending = asyncio.create_task(session.announce('先取消这次提醒'))
    await asyncio.sleep(.01)
    assert not frames
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    session.state = 'ready'
    await asyncio.sleep(.06)
    assert not frames and not messages
    session.state = 'speaking'
    pending = asyncio.create_task(session.announce('时间到了'))
    await asyncio.sleep(.01)
    session.state = 'ready'
    session._record_state()
    await pending
    assert len(frames) == 1 and '时间到了' in frames[0]['text']
    monkeypatch.setattr('duckking.voice.RESPONSE_TIMEOUT', .01)
    session.state = 'speaking'
    await session.announce('等待已超时')
    assert len(frames) == 1 and messages[-1]['spoken'] is False


async def test_speech_interruption_preserves_solo_but_explicit_stop_cancels(studio, tmp_path):
    await studio.select('conductor')
    playing = asyncio.Event()
    async def concert():
        playing.set()
        await asyncio.Event().wait()
    task = await studio.start('conductor', concert)
    await playing.wait()
    async def send(data):
        pass
    session = VoiceSession(send, studio.motion, Settings(data_dir=tmp_path))
    before = len(studio.motion.records)
    session.pending_input = {'frames': []}
    await session._stop_motion()
    assert not task.done() and len(studio.motion.records) == before
    session.pending_input = None
    await session._stop_motion()
    assert task.done() and studio.state['status'] == 'cancelled'
    stopped = list(studio.motion.records.values())[before:]
    assert stopped and all(r["name"] == "stop" and r["status"] == "completed" for r in stopped)

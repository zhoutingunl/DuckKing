import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from duckking.app import create_app
from duckking.config import Settings
from duckking.language_setup import setup_language_profile
from duckking.motion import MotionController, PreviewBackend
from duckking.voice import VoiceSession
from duckking.voice_profiles import language_agent, public_profiles, store_profiles


def configured(path):
    store_profiles(path / 'voice-profiles.json', {'voices': {}, 'agents': {
        'language_fr': {'id': 'private-fr'}, 'language_en': {'id': 'private-en'},
        'language_zh': {'id': 'private-zh'}, 'studio': {'id': 'private-studio'},
    }})
    return Settings(data_dir=path)


@pytest.mark.parametrize('language', ['fr', 'en', 'zh'])
async def test_language_selects_private_handshake_without_rebinding(tmp_path, language):
    settings = configured(tmp_path)
    messages, headers = [], []
    release = asyncio.Event()

    async def cloud(ws):
        headers.append(ws.request.headers.get('X-Agent-ID'))
        hello = json.loads(await ws.recv())
        assert hello['type'] == 'hello'
        await ws.send(json.dumps({'type': 'hello', 'transport': 'websocket',
                                 'session_id': 'fixture', 'audio_params': {'format': 'pcm'}}))
        await release.wait()

    async def send(message):
        messages.append(message)

    async with serve(cloud, '127.0.0.1', 0) as server:
        settings.ws_url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        settings.ws_token = 'fixture-token'
        voice = VoiceSession(send, MotionController(PreviewBackend()), settings)
        voice.set_language(language)
        try:
            await voice.open()
            assert voice.state == 'ready'
            assert headers == [f'private-{language}']
            assert voice.status()['language'] == language
            assert voice.diagnostic_status()['language'] == language
            attempts = [e for e in voice.diagnostics.events if e['event'] == 'cloud_connect']
            assert [(e['language'], e['agent_profile']) for e in attempts] == [
                (language, f'language_{language}'),
            ]
            assert 'private-' not in json.dumps(messages)
            assert 'private-' not in json.dumps(voice.diagnostics.snapshot())
            with pytest.raises(ValueError, match='先断开'):
                voice.set_language('zh')
        finally:
            release.set()
            await voice.disconnect()
    assert public_profiles(settings)['personas'] == []


async def test_language_survives_cloud_close_and_reconnect_in_same_room(tmp_path):
    settings = configured(tmp_path)
    attempts, messages = [], []
    closed = asyncio.Event()
    terminal = asyncio.Event()

    async def cloud(ws):
        attempts.append(ws.request.headers.get('X-Agent-ID'))
        await ws.recv()
        await ws.send(json.dumps({'type': 'hello', 'transport': 'websocket',
                                 'session_id': 'fixture', 'audio_params': {'format': 'pcm'}}))
        if len(attempts) == 2:
            await closed.wait()
            await ws.close()
        else:
            await ws.wait_closed()

    async def send(message):
        messages.append(message)
        if message.get('state') in {'error', 'disconnected'}:
            terminal.set()

    async with serve(cloud, '127.0.0.1', 0) as server:
        settings.ws_url = f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        settings.ws_token = 'fixture-token'
        voice = VoiceSession(send, MotionController(PreviewBackend()), settings)
        try:
            voice.set_language('zh')
            await voice.open()
            await voice.disconnect()
            voice.set_language('fr')
            await voice.open()
            closed.set()
            await asyncio.wait_for(terminal.wait(), 5)
            await voice.open()
            assert voice.state == 'ready'
            assert voice.language == 'fr'
            assert attempts == ['private-zh', 'private-fr', 'private-fr']
            log = [e for e in voice.diagnostics.events if e['event'] == 'cloud_connect']
            assert [e['language'] for e in log] == ['zh', 'fr', 'fr']
            assert [e['agent_profile'] for e in log] == [
                'language_zh', 'language_fr', 'language_fr',
            ]
        finally:
            closed.set()
            await voice.disconnect()


@pytest.mark.parametrize('language', ['fr', 'en', 'de', ['fr']])
def test_missing_or_invalid_language_never_falls_back_to_chinese(tmp_path, language):
    with pytest.raises(ValueError):
        language_agent(Settings(data_dir=tmp_path), language)


def test_browser_language_uses_cloud_not_chinese_offline_model(tmp_path, monkeypatch):
    settings = configured(tmp_path)
    seen = []

    def start(self, **kwargs):
        seen.append((type(self).__name__, self.language))
    monkeypatch.setattr(VoiceSession, 'start_connect', start)
    with TestClient(create_app(settings=settings)) as client:
        with client.websocket_connect('/voice?room=1') as ws:
            ws.receive_json()
            ws.send_json({'type': 'connect', 'language': 'fr', 'mode': 'local_first'})
            ws.send_json({'type': 'ping'})
            assert ws.receive_json()['type'] == 'pong'
    assert seen == [('VoiceSession', 'fr')]


async def test_language_setup_checks_voice_asr_and_never_binds_device(tmp_path):
    key = tmp_path / 'key'
    key.write_text('test-key')
    settings = Settings(data_dir=tmp_path / 'data')
    calls, agent = [], {}

    def handler(request):
        path = request.url.path
        calls.append((request.method, path))
        if path.endswith('/agent/list'):
            data = []
        elif path == '/v1/voices':
            data = {'voices': [
                {'id': 'wrong-zh', 'tags': {'languages': ['zh']}},
                {'id': 'valid-fr', 'tags': {'languages': ['fr']}, 'tier': 'pro'},
            ]}
        elif request.method == 'POST':
            agent.update(json.loads(request.content))
            data = 'private-new-fr'
        elif request.method == 'PUT':
            agent.update(json.loads(request.content))
            data = None
        else:
            data = agent
        return httpx.Response(200, json={'code': 0, 'data': data})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await setup_language_profile(settings, key, 'fr', http=http)
    assert result['voice_verified'] is False  # configuration is not a voice test
    assert agent['ttsVoiceId'] == 'valid-fr'
    assert agent['extra']['asr']['enable_auto_lang'] is True
    assert 'Réponds toujours en français' in agent['systemPrompt']
    assert '简短自然中文确认' not in agent['systemPrompt']
    assert not any('/device/' in path or '/ota' in path for _, path in calls)
    assert language_agent(settings, 'fr') == 'private-new-fr'
    assert 'private-' not in json.dumps(result)


async def test_unverified_clones_and_personas_cannot_override_french(tmp_path):
    settings = configured(tmp_path)
    store_profiles(tmp_path / 'voice-profiles.json', {'voices': {
        'chinese-only': {'id': 'private-clone'},
        'french-verified': {'id': 'private-fr-voice', 'languages': ['fr']},
    }, 'agents': {'language_fr': {'id': 'private-fr'}, 'coach': {'id': 'private-coach'}}})
    messages = []

    async def send(message):
        messages.append(message)

    voice = VoiceSession(send, MotionController(PreviewBackend()), settings)
    voice.set_language('fr')
    assert [v['key'] for v in public_profiles(settings, 'fr')['voices']] == ['french-verified']
    assert public_profiles(settings, 'fr')['personas'] == []
    with pytest.raises(ValueError, match='当前对话语言'):
        await voice.set_style({'profile': 'chinese-only'})
    with pytest.raises(ValueError, match='当前对话语言'):
        voice.set_persona({'persona': 'coach'})
    assert voice.voice_style is None and voice.persona == 'default'
    await voice.set_style({'profile': 'french-verified'})
    assert voice.voice_style['id'] == 'private-fr-voice'
    assert 'private-' not in json.dumps(messages)


def test_missing_language_reports_error_and_releases_room(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(VoiceSession, 'start_connect', lambda self: seen.append(self.language))
    with TestClient(create_app(settings=Settings(data_dir=tmp_path))) as client:
        with client.websocket_connect('/voice?room=1') as ws:
            assert ws.receive_json()['state'] == 'disconnected'
            ws.send_json({'type': 'connect', 'language': 'fr'})
            error = ws.receive_json()
            assert error['type'] == 'error' and '尚未配置' in error['message']
        with client.websocket_connect('/voice?room=1') as ws:
            assert ws.receive_json()['state'] == 'disconnected'
            ws.send_json({'type': 'connect', 'language': 'zh'})
            ws.send_json({'type': 'ping'})
            assert ws.receive_json()['type'] == 'pong'
    assert seen == ['zh']


@pytest.mark.parametrize('state', ['error', 'awaiting_binding'])
def test_language_reconnect_from_error_or_activation_is_allowed(tmp_path, state):
    voice = VoiceSession(None, MotionController(PreviewBackend()), configured(tmp_path))
    voice.state = state
    voice.set_language('fr')
    assert voice.language == 'fr'


def test_explicit_language_profiles_require_a_chinese_profile_too(tmp_path):
    store_profiles(tmp_path / 'voice-profiles.json', {'agents': {
        'language_fr': {'id': 'private-fr'},
    }})
    with pytest.raises(ValueError, match='尚未配置'):
        language_agent(Settings(data_dir=tmp_path), 'zh')

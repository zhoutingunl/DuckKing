import json

import httpx
import pytest
from websockets.asyncio.server import serve

from duckking.config import Settings
from duckking.language_device import device_settings, setup_language_device, voice_settings
from duckking.motion import MotionController, PreviewBackend
from duckking.voice import VoiceSession
from duckking.voice_profiles import store_profiles


def configured(path):
    store_profiles(path / 'voice-profiles.json', {'agents': {
        'language_fr': {'id': 'private-fr', 'transport': 'bound_device'},
        'language_zh': {'id': 'private-zh'},
    }})
    return Settings(data_dir=path, ws_url='wss://old.example/ws', ws_token='old-secret',
                    device_id='02:00:00:00:00:01',
                    client_id='00000000-0000-4000-8000-000000000001')


def prepare(settings, language='fr'):
    selected = device_settings(settings, language)
    identity = selected.identity()
    marker = selected.data_dir / 'binding.json'
    marker.write_text(json.dumps({'language': language, 'agent_id': f'private-{language}',
                                  'device_id': identity['device_id']}))
    return selected


def test_language_identities_are_private_stable_and_distinct_per_room(tmp_path):
    settings = configured(tmp_path)
    original = settings.identity()
    identities = set()
    for room in ['1', '2']:
        for language in ['en', 'fr']:
            s = device_settings(settings.for_room(room), language)
            assert s.ws_url == s.ws_token == s.device_id == s.client_id == ''
            assert s.identity() == s.identity()
            identities.add(s.identity()['device_id'])
            assert (s.data_dir / 'identity.json').stat().st_mode & 0o777 == 0o600
    assert len(identities) == 4
    assert original['device_id'] not in identities
    assert settings.identity() == original
    assert voice_settings(settings, 'zh', 'private-zh') is settings


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'wrong_agent', 'wrong_device'])
def test_missing_or_mismatched_binding_never_uses_chinese_device(tmp_path, failure):
    settings = configured(tmp_path)
    selected = device_settings(settings, 'fr')
    if failure != 'missing':
        prepare(settings)
        marker = selected.data_dir / 'binding.json'
        data = json.loads(marker.read_text())
        if failure == 'wrong_agent':
            data['agent_id'] = 'private-zh'
        elif failure == 'wrong_device':
            data['device_id'] = '02:00:00:00:00:ff'
        marker.write_text('broken' if failure == 'corrupt' else json.dumps(data))
    voice = VoiceSession(None, MotionController(PreviewBackend()), settings)
    with pytest.raises(ValueError, match='尚未准备'):
        voice.set_language('fr')
    assert voice.language is None
    if failure == 'missing':
        assert not selected.data_dir.exists()  # ordinary connects never provision


async def test_bound_transport_uses_verified_device_not_root_overrides(tmp_path, monkeypatch):
    settings = configured(tmp_path)
    selected = prepare(settings)
    seen, messages = [], []

    async def cloud(ws):
        seen.append((ws.request.headers['Device-Id'], ws.request.headers['X-Agent-ID']))
        await ws.recv()
        await ws.send(json.dumps({'type': 'hello', 'transport': 'websocket',
                                 'audio_params': {'format': 'pcm'}}))
        await ws.wait_closed()

    async def send(message):
        messages.append(message)

    async with serve(cloud, '127.0.0.1', 0) as server:
        async def provision(s, http):
            assert s.data_dir == selected.data_dir
            assert s.ws_token == s.device_id == s.client_id == ''
            return {'identity': s.identity(), 'websocket': {
                'url': f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}', 'token': 'secret',
            }}
        monkeypatch.setattr('duckking.voice.provision', provision)
        voice = VoiceSession(send, MotionController(PreviewBackend()), settings)
        voice.set_language('fr')
        try:
            await voice.open()
            assert voice.state == 'ready'
            await voice.disconnect()
            await voice.open()
            assert seen == [(selected.identity()['device_id'], 'private-fr')] * 2
            events = [e for e in voice.diagnostics.events if e['event'] == 'cloud_connect']
            assert all(e['device_route'] == 'language_device' for e in events)
            serialized = json.dumps(messages) + json.dumps(voice.diagnostics.snapshot())
            assert selected.identity()['device_id'] not in serialized
            assert 'private-fr' not in serialized and 'old-secret' not in serialized
        finally:
            await voice.disconnect()


@pytest.mark.parametrize('bound_correctly', [True, False])
async def test_setup_verifies_binding_without_rebinding_existing_room(tmp_path, bound_correctly):
    settings = configured(tmp_path)
    original = settings.identity()
    key = tmp_path / 'key'
    key.write_text('private-key')
    calls = []
    selected = device_settings(settings, 'fr')

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == '/xiaozhi/agent/list':
            data = [{'id': 'private-fr', 'agentName': 'DuckKing-fr'}]
        elif request.url.path == '/v1/ota/':
            return httpx.Response(200, json={'websocket': {'url': 'wss://example.com/ws',
                                                         'token': 'private-token'}})
        else:
            assert request.method == 'GET'
            assert request.url.path == '/xiaozhi/device/bind/private-fr'
            data = [{'macAddress': selected.identity()['device_id']}] if bound_correctly else []
        return httpx.Response(200, json={'code': 0, 'data': data})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        if bound_correctly:
            result = await setup_language_device(settings, key, 'fr', http=http)
            assert result['status'] == 'language_device_ready'
            assert result['voice_verified'] is False
            assert 'private-' not in json.dumps(result)
            assert voice_settings(settings, 'fr', 'private-fr').identity() == selected.identity()
            assert (selected.data_dir / 'binding.json').stat().st_mode & 0o777 == 0o600
        else:
            with pytest.raises(ValueError, match='绑定校验失败'):
                await setup_language_device(settings, key, 'fr', http=http)
            assert not (selected.data_dir / 'binding.json').exists()
    assert settings.identity() == original
    assert not any(method != 'GET' and path.startswith('/xiaozhi/device/')
                   for method, path in calls)

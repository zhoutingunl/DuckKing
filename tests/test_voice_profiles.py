import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from duckking.app import create_app
from duckking.config import Settings
from duckking.motion import MotionController, PreviewBackend
from duckking.voice import VoiceSession
from duckking.voice_profiles import public_profiles, store_profiles


def configure(tmp_path):
    store_profiles(tmp_path / 'voice-profiles.json', {
        'voices': {'duck-raspy': {'id': 'private-voice-fixture', 'label': '鸭嗓'}},
        'agents': {'coach': {'id': 'private-agent-fixture', 'label': '严教练'}}})


def test_public_profiles_and_rooms_exclude_private_ids(tmp_path):
    configure(tmp_path)
    settings = Settings(data_dir=tmp_path)
    result = public_profiles(settings.for_room('3'))
    assert result['voices'][0]['key'] == 'duck-raspy'
    assert 'private-' not in json.dumps(result)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get('/api/voice/profiles')
        assert response.status_code == 200
        assert 'private-' not in response.text


async def test_profile_is_sent_on_listen_and_agent_only_in_handshake(tmp_path):
    configure(tmp_path)
    messages, frames = [], []
    got_frame = asyncio.Event()
    release = asyncio.Event()
    async def cloud(ws):
        assert ws.request.headers['X-Agent-ID'] == 'private-agent-fixture'
        assert 'Voice-Id' not in ws.request.headers
        await ws.recv()
        await ws.send(json.dumps({'type': 'hello', 'transport': 'websocket',
                                   'session_id': 'fixture',
                                   'audio_params': {'format': 'pcm', 'sample_rate': 16000}}))
        frames.append(json.loads(await ws.recv()))
        got_frame.set()
        await release.wait()
    async def send(value):
        messages.append(value)
    async with serve(cloud, '127.0.0.1', 0) as server:
        port = server.sockets[0].getsockname()[1]
        voice = VoiceSession(send, MotionController(PreviewBackend()), Settings(
            data_dir=tmp_path, ws_url=f'ws://127.0.0.1:{port}', ws_token='fixture-token'))
        voice.set_persona({'persona': 'coach'})
        await voice.set_style({'profile': 'duck-raspy', 'pitch': 1.04})
        try:
            await voice.open()
            await voice.listen(True)
            await asyncio.wait_for(got_frame.wait(), 3)
            assert frames[0]['state'] == 'start'
            assert frames[0]['agent_params']['voice']['id'] == 'private-voice-fixture'
            assert frames[0]['agent_params']['voice']['pitch'] == 1.04
            assert 'private-' not in json.dumps(messages)
            with pytest.raises(ValueError):
                await voice.set_style({'profile': 'unknown'})
        finally:
            release.set()
            await voice.disconnect()

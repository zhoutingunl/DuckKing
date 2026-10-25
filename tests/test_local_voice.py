"""Whole-sentence routing, exact audio handoff, interruption and bounded admission."""

import asyncio
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from duckking import asr_client
from duckking.app import create_app
from duckking.asr_service import MAX_BYTES, create_asr_app
from duckking.config import Settings
from duckking.hybrid_voice import HybridVoiceSession
from duckking.local_commands import parse_commands
from duckking.motion import MotionController, PreviewBackend


@pytest.mark.parametrize('text,names', [
    ('向前走再向左转再向右转', ['walk', 'turn_left', 'turn_right']),
    ('小鸭，请后退两秒，然后点点头！', ['backward', 'nod']),
    ('停止', ['stop']), ('不要动', ['stop']),
    ('进入动作练习场，先前滚翻，再低头啄取，最后摇头',
     ['scene_skills', 'roulade', 'ground_pick', 'shake_head']),
    ('鸭B前进，鸭A点头', ['walk', 'nod']),
])
def test_complete_grammar(text, names):
    plan = parse_commands(text, physical=True, scene='duo')
    assert [a.name for a in plan.actions] == names
    if '两秒' in text:
        assert plan.actions[0].duration == 2
    if '鸭B' in text:
        assert plan.actions[0].target == 'b'


@pytest.mark.parametrize('text', [
    '不要前进', '先前进然后去火星', '前进吗', '如果有球就前进',
    '前进四秒', '前进30秒', '先前进再左转然后不要右转', '啄取还是摇头',
    '先前进再前进再前进再前进再前进再前进再前进', '?前进', '',
    '前滚翻再前滚翻再前滚翻再前滚翻', '右转' * 100,
])
def test_unknown_suffix_negation_question_and_limits_never_partially_execute(text):
    assert not parse_commands(text, physical=True, scene='skills').actions


@pytest.mark.parametrize('text,physical,scene', [
    ('坐下', False, None), ('前滚翻', True, 'ball'), ('左脚踢球', True, 'duo'),
    ('鸭B前进', True, 'ball'), ('前进', True, 'table'), ('前进', True, 'rollers'),
    ('前进', True, 'carry'),
])
def test_context_checked_before_any_action(text, physical, scene):
    assert not parse_commands(text, physical=physical, scene=scene).actions


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(.01)


def session(tmp_path):
    messages = []

    async def send(data):
        messages.append(data)

    voice = HybridVoiceSession(send, MotionController(PreviewBackend()),
                               Settings(data_dir=tmp_path))
    return voice, messages


async def utter(voice, frames=1):
    await voice.listen(True)
    for i in range(frames):
        await voice.audio(bytes([i % 256]) * 1920)
    await voice.listen(False)
    await voice.processing


async def test_local_actions_do_not_open_cloud_or_count_tts(tmp_path, monkeypatch):
    async def recognize(pcm):
        return dict(text='前进0.2秒，然后左转0.2秒，再右转0.2秒', speech=True, asr_ms=120)

    async def forbidden(*args, **kwargs):
        pytest.fail('Local match must never open cloud')

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    monkeypatch.setattr(HybridVoiceSession, '_open_transport', forbidden)
    voice, messages = session(tmp_path)
    await voice.open()
    try:
        await utter(voice)
        snapshot = voice.diagnostics.statistics.snapshot()
        assert snapshot['routing']['local'] == 1
        assert snapshot['counts']['completed_actions'] == 3
        assert snapshot['counts']['replied'] == 0
        assert snapshot['latencies']['local_asr']['p50_ms'] == 120
        assert snapshot['routing']['action_latency']['local']['count'] == 1
        assert voice.uplink_frames == voice.downlink_frames == 0
        assert voice.state == 'ready'
        assert all(m.get('source') == 'local' for m in messages if m['type'] == 'transcript')
    finally:
        await voice.disconnect()
        await voice.motion.close()


@pytest.mark.parametrize('failure', ['unmatched', 'timeout', 'unavailable'])
async def test_fallback_uploads_original_audio_once(tmp_path, monkeypatch, failure):
    sent, encoded = [], []

    async def recognize(pcm):
        if failure == 'timeout':
            raise httpx.ReadTimeout('private token')
        if failure == 'unavailable':
            raise httpx.ConnectError('private token')
        return dict(text='先前进然后去火星', speech=True, asr_ms=80)

    class Cloud:
        async def send(self, data):
            sent.append(data)

        async def close(self):
            pass

    class Encoder:
        def encode(self, pcm):
            encoded.append(pcm)
            return pcm

        def close(self):
            pass

    async def connect(self, **kwargs):
        self.cloud, self.encoder, self.state = Cloud(), Encoder(), 'ready'

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    monkeypatch.setattr(HybridVoiceSession, '_open_transport', connect)
    voice, _ = session(tmp_path)
    await voice.open()
    try:
        await utter(voice, 3)
        assert encoded == [bytes([i]) * 1920 for i in range(3)]
        assert [json.loads(x)['state'] for x in sent if isinstance(x, str)] == ['start', 'stop']
        snapshot = voice.diagnostics.statistics.snapshot()
        assert snapshot['counts']['actions'] == 0
        assert snapshot['routing']['fallback'] == 1
        assert len(snapshot['rounds']) == 1
        assert 'private' not in str(snapshot)
    finally:
        await voice.disconnect()
        await voice.motion.close()


async def test_failed_local_action_does_not_replay_to_cloud(tmp_path, monkeypatch):
    async def recognize(pcm):
        return dict(text='前进再点头', speech=True, asr_ms=1)

    async def failed(*args):
        raise RuntimeError('private-device-token')

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    voice, messages = session(tmp_path)
    monkeypatch.setattr(voice.motion.backend, 'move', failed)
    await voice.open()
    try:
        await utter(voice)
        stats = voice.diagnostics.statistics.snapshot()
        assert stats['routing']['fallback'] == 0
        assert stats['counts']['actions'] == 1
        assert stats['counts']['errors'] == 1
        assert 'private-device' not in str(messages)
    finally:
        await voice.disconnect()
        await voice.motion.close()


async def test_interrupt_cancels_pending_asr_and_preserves_new_input(tmp_path, monkeypatch):
    entered = asyncio.Event()
    calls = []

    async def recognize(pcm):
        calls.append(pcm)
        if len(calls) == 1:
            entered.set()
            await asyncio.Event().wait()
        return dict(text='停止', speech=True, asr_ms=1)

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    voice, _ = session(tmp_path)
    await voice.open()
    try:
        await voice.listen(True)
        await voice.audio(bytes(1920))
        await voice.listen(False)
        await entered.wait()
        voice.start_interrupt()
        await voice.listen(True)
        await voice.audio(b'\x01' * 1920)
        await voice.listen(False)
        await voice.connector
        await voice.processing
        stats = voice.diagnostics.statistics.snapshot()
        assert calls == [bytes(1920), b'\x01' * 1920]
        assert stats['counts']['interrupted'] == 1
        assert stats['counts']['completed_actions'] == 1
        assert voice.generation == 1
    finally:
        await voice.disconnect()
        await voice.motion.close()


async def test_disconnect_stops_running_local_action(tmp_path, monkeypatch):
    async def recognize(pcm):
        return dict(text='前进三秒再左转', speech=True, asr_ms=1)

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    voice, _ = session(tmp_path)
    await voice.open()
    await voice.listen(True)
    await voice.audio(bytes(1920))
    await voice.listen(False)
    await eventually(lambda: voice.motion.current is not None)
    await voice.disconnect()
    assert voice.motion.current is None
    assert voice.state == 'disconnected'
    assert not voice.frames
    actions = voice.diagnostics.statistics.snapshot()['rounds'][0]['actions']
    assert actions[0]['result'] == 'cancelled'
    await voice.motion.close()


async def test_empty_silence_frame_validation_and_recording_cap(tmp_path, monkeypatch):
    received = []

    async def recognize(pcm):
        received.append(pcm)
        return dict(text='', speech=False, asr_ms=1)

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    voice, _ = session(tmp_path)
    await voice.open()
    try:
        await utter(voice, 0)
        assert not received
        await voice.listen(True)
        with pytest.raises(ValueError):
            await voice.audio(b'odd')
        for _ in range(251):
            await voice.audio(bytes(1920))
        await voice.processing
        assert len(received) == 1 and len(received[0]) == MAX_BYTES
        assert voice.route == 'no_speech' and voice.state == 'ready'
    finally:
        await voice.disconnect()
        await voice.motion.close()


def test_worker_protocol_bounds_and_failure():
    def recognize(pcm):
        raise RuntimeError('private-token')

    with TestClient(create_asr_app(recognize=recognize)) as client:
        assert client.get('/health').json()['ready'] is True
        assert client.post('/recognize', content=b'odd').status_code == 415
        headers = {'Content-Type': 'application/octet-stream'}
        for data, status in [(b'odd', 400), (bytes(MAX_BYTES + 1), 413), (bytes(1920), 503)]:
            response = client.post('/recognize', headers=headers, content=data)
            assert response.status_code == status
            assert 'private' not in response.text


async def test_worker_admission_stays_bounded_after_client_cancellation():
    gate = threading.Event()

    def recognize(pcm):
        gate.wait(3)
        return dict(text='点头', speech=True)

    app = create_asr_app(recognize=recognize)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url='http://test') as client:
            async def request():
                return await client.post('/recognize', content=bytes(1920),
                                         headers={'Content-Type': 'application/octet-stream'})
            tasks = [asyncio.create_task(request()) for _ in range(2)]
            try:
                for _ in range(100):
                    if (await client.get('/health')).json()['pending'] == 2:
                        break
                    await asyncio.sleep(.01)
                tasks[0].cancel()
                await asyncio.gather(tasks[0], return_exceptions=True)
                assert (await request()).status_code == 503
                gate.set()
                assert (await tasks[1]).status_code == 200
            finally:
                gate.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


def test_mode_endpoint_and_two_room_ownership(tmp_path, monkeypatch):
    async def availability():
        return dict(available=True, engine='test')

    monkeypatch.setattr(asr_client, 'availability', availability)
    app = create_app(settings=Settings(data_dir=tmp_path, local_asr=True))
    with TestClient(app) as client:
        assert client.get('/api/voice/modes').json()['local_first'] is True
        with client.websocket_connect('/voice?room=1') as one:
            one.receive_json()
            one.send_json({'type': 'connect', 'mode': 'local_first'})
            assert one.receive_json()['state'] == 'ready'
            with client.websocket_connect('/voice?room=2') as two:
                two.receive_json()
                two.send_json({'type': 'connect', 'mode': 'local_first'})
                assert two.receive_json()['state'] == 'ready'
                one.send_json({'type': 'connect', 'mode': 'cloud'})
                assert one.receive_json()['type'] == 'error'
                one.send_json({'type': 'disconnect'})
                assert one.receive_json()['state'] == 'disconnected'
                two.send_json({'type': 'ping'})
                assert two.receive_json()['type'] == 'pong'


def test_real_pinned_model_recognizes_commands_and_preserves_negation():
    import runpy
    from pathlib import Path

    pytest.importorskip('sherpa_onnx')
    root = Path(__file__).resolve().parents[1]
    if not (root / 'external/asr/model.int8.onnx').exists():
        pytest.skip('Run scripts/fetch_asr_assets.py for real model verification')
    result = runpy.run_path(str(root / 'scripts/verify_local_asr.py'))['verify']()
    assert result['synthetic_fixtures'] is True


@pytest.mark.parametrize('payload', [[], {}, {'text': 1}, {'text': '点头', 'speech': 'yes'}])
async def test_worker_client_rejects_malformed_results(monkeypatch, payload):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    monkeypatch.setattr(asr_client.httpx, 'AsyncClient',
                        lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(ValueError):
        await asr_client.recognize(bytes(1920))


async def test_worker_client_health_and_real_elapsed_time(monkeypatch):
    original = httpx.AsyncClient

    def respond(request):
        if request.url.path == '/health':
            return httpx.Response(200, json={'ready': True, 'engine': 'untrusted-token'})
        assert request.content == bytes(1920)
        return httpx.Response(200, json={'text': '点头', 'speech': True, 'asr_ms': -1})

    monkeypatch.setattr(asr_client.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(respond), **kwargs
    ))
    assert (await asr_client.availability()) == {
        'available': True, 'engine': 'sherpa-onnx/SenseVoiceSmall-INT8'
    }
    assert (await asr_client.recognize(bytes(1920)))['asr_ms'] >= 0


@pytest.mark.parametrize('binding', [True, False])
async def test_cloud_handoff_activation_and_failure_do_not_retain_recording(tmp_path, monkeypatch,
                                                                         binding):
    async def recognize(pcm):
        return dict(text='今天天气怎么样', speech=True, asr_ms=1)

    async def connect(self, **kwargs):
        if binding:
            self.state = 'awaiting_binding'
            await self.publish_status()
        else:
            raise TimeoutError('private-cloud-url')

    monkeypatch.setattr(asr_client, 'recognize', recognize)
    monkeypatch.setattr(HybridVoiceSession, '_open_transport', connect)
    voice, messages = session(tmp_path)
    await voice.open()
    try:
        await utter(voice)
        assert voice.state == ('awaiting_binding' if binding else 'error')
        assert not voice.frames and voice.cloud is None
        assert 'private-cloud-url' not in str(messages)
    finally:
        await voice.disconnect()
        await voice.motion.close()

import json
import queue
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.config import Settings
from duckking.diagnostics import VoiceDiagnostics
from duckking.experience import (
    ExperienceContext,
    ExperienceEvent,
    ExperienceStore,
    VoiceExperience,
)


def event(**values):
    return ExperienceEvent(id=uuid.uuid4(), sequence=1, kind="voice", status="completed",
                           traffic="interactive", page="scenarios", device="mobile", **values)


def save(store, value, room="1", source="browser"):
    assert store.submit(value, source=source, room=room)
    store.flush()


def test_persistence_exact_percentiles_filtering_no_missing_zeroes_and_private_data(tmp_path):
    path = tmp_path / 'experience.sqlite3'
    store = ExperienceStore(path, 'a'*40)
    for i in range(1, 21):
        save(store, event(route='local', metrics={'stt_local_ms': i*10}))
    empty = event(route='cloud')
    save(store, empty, room='2')
    cloud = event(route='cloud_fallback', metrics={'stt_cloud_ms': 250})
    save(store, cloud, source='server')
    save(store, event(route='local', metrics={'asr_ms': 9}).model_copy(
        update={'traffic': 'verification'}))
    store.close()
    restarted = ExperienceStore(path, 'b'*40)
    try:
        report = restarted.snapshot()
        assert report['samples'] == 22 and report['storage_ok']
        local = next(g for g in report['groups'] if g['metric'] == 'stt_local_ms')
        assert local == dict(source='browser', metric='stt_local_ms', route='local', count=20,
                             mean_ms=105.0, p50_ms=100, p90_ms=180, p95_ms=190)
        assert report['collection_started_at'] and len(report['trend']) == 2
        assert restarted.snapshot(room='2')['groups'] == []
        assert restarted.snapshot(release='b'*40)['samples'] == 0
        assert restarted.snapshot(device='desktop')['samples'] == 0
        assert restarted.snapshot(traffic='verification')['samples'] == 1
        assert restarted.snapshot(page='home')['samples'] == 0
        assert restarted.snapshot(cache='network')['samples'] == 0
        assert restarted.snapshot(backend='robotd')['samples'] == 0
        assert restarted.snapshot(scene='ball')['samples'] == 0
        exported = json.dumps(report)
        for forbidden in [str(empty.id), str(cloud.id), 'transcript', 'audio_data', 'token']:
            assert forbidden not in exported
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        restarted.close()


def test_retry_and_out_of_order_updates_are_idempotent_and_room_release_cannot_change(tmp_path):
    store = ExperienceStore(tmp_path/'e.db')
    first = event(route='local', metrics={'stt_local_ms': 100})
    try:
        save(store, first)
        final = first.model_copy(update={'sequence': 3, 'metrics': {'stt_local_ms': 100,
                                                                  'action_ms': 300}})
        with ThreadPoolExecutor(5) as pool:
            list(pool.map(lambda _: store.submit(final, source='browser', room='1'), range(20)))
        save(store, first.model_copy(update={'sequence': 2, 'status': 'failed'}), room='2')
        report = store.snapshot()
        assert report['samples'] == 1 and report['statuses'] == {'completed': 1}
        assert {g['metric'] for g in report['groups']} == {'stt_local_ms', 'action_ms'}
        assert store.snapshot(room='2')['samples'] == 0
        assert all(g['count'] == 1 for g in report['groups'])
    finally:
        store.close()


def test_failed_loads_do_not_improve_latency_and_unfinished_records_expire(tmp_path):
    store = ExperienceStore(tmp_path/'e.db')
    try:
        for status in ['completed', 'failed', 'cancelled', 'timeout', 'started', 'waiting']:
            save(store, event().model_copy(update={'kind': 'load', 'status': status,
                                                  'metrics': {'scene_ms': 1000}}))
        report = store.snapshot(now=time.time()+181)
        assert report['statuses']['abandoned'] == 2
        assert report['groups'][0]['count'] == 1
        assert report['groups'][0]['mean_ms'] == 1000
        assert len(report['outcomes']) == 5
    finally:
        store.close()


def test_retention_and_capacity_are_bounded(tmp_path):
    store = ExperienceStore(tmp_path/'e.db', capacity=3)
    try:
        for _ in range(5):
            save(store, event())
        assert store.snapshot()['samples'] == 3
        with sqlite3.connect(store.path) as db:
            db.execute('UPDATE samples SET at=?', (time.time()-91*86400,))
        save(store, event(metrics={'asr_ms': 12}))
        assert store.snapshot()['samples'] == 1
        with sqlite3.connect(store.path) as db:
            assert db.execute('SELECT COUNT(*) FROM samples').fetchone()[0] == 1
    finally:
        store.close()


def test_disk_errors_and_queue_overflow_do_not_raise_into_voice(tmp_path, monkeypatch):
    store = ExperienceStore(tmp_path/'e.db')
    connect = store._connect
    monkeypatch.setattr(store, '_connect', lambda: (_ for _ in ()).throw(OSError('private path')))
    save(store, event())
    assert not store.storage_ok and store.dropped == 1
    monkeypatch.setattr(store, '_connect', connect)
    save(store, event())
    assert store.snapshot()['storage_ok']
    monkeypatch.setattr(store.queue, 'put_nowait', lambda _: (_ for _ in ()).throw(queue.Full()))
    assert not store.submit(event(), source='browser', room='1')
    assert store.dropped == 2
    store.close()
    assert not store.submit(event(), source='browser', room='1')
    store.path.write_text('invalid database')
    assert not store.snapshot()['storage_ok']


def test_server_journal_tracks_fallback_separately_without_storing_speech(tmp_path):
    store = ExperienceStore(tmp_path/'e.db')
    sink = VoiceExperience(store, '2')
    journal = VoiceDiagnostics(experience=sink)
    sink.pending = ExperienceContext(id=uuid.uuid4(), traffic='interactive', page='studio')
    def record(name, elapsed=0, **fields):
        journal.record(name, turn=1, backend='preview', elapsed_ms=elapsed, **fields)
    record('listen_start', mode='local_first')
    record('listen_stop', 1000)
    record('local_asr', 1200, asr_ms=199)
    record('stt', 1250, source='local', text='PRIVATE USER SPEECH')
    record('voice_route', 1260, route='cloud_fallback', reason='unmatched')
    record('stt', 1500, text='PRIVATE USER SPEECH')
    record('action_start', 2000, call=1, tool='duck_nod')
    record('downlink_first_frame', 2300)
    record('tts_stop', 3000, result='ok')
    record('state', 3100, state='disconnected')
    store.flush()
    result = store.snapshot()
    assert result['samples'] == 1 and result['statuses'] == {'completed': 1}
    assert {g['metric']: g['p50_ms'] for g in result['groups']} == {
        'asr_ms': 199, 'stt_local_ms': 250, 'stt_cloud_ms': 500,
        'action_ms': 1000, 'audio_ms': 1300, 'reply_ms': 2000,
    }
    assert {g['route'] for g in result['groups']} == {'cloud_fallback'}
    with sqlite3.connect(store.path) as db:
        assert 'PRIVATE USER SPEECH' not in str(db.execute('SELECT * FROM samples').fetchall())
    store.close()


def test_api_validation_limits_origin_and_restart(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings=settings)
    payload = {'events': [event(metrics={'stt_local_ms': 333}).model_dump(mode='json')]}
    with TestClient(app) as client:
        assert client.post('/api/experience?room=2', json=payload).status_code == 202
        app.state.experience.flush()
        assert client.get('/api/experience?room=2').json()['groups'][0]['mean_ms'] == 333
        assert client.get('/api/experience').headers['cache-control'] == 'no-store'
        assert client.post('/api/experience', json=payload,
                           headers={'Origin': 'https://elsewhere.example'}).status_code == 403
        for mutate in [lambda d: d.update(text='secret'),
                       lambda d: d.update(metrics={'secret': 4}),
                       lambda d: d.update(metrics={'action_ms': -1}),
                       lambda d: d.update(metrics={'action_ms': 86400001}),
                       lambda d: d.update(device='iPhone raw UA'),
                       lambda d: d.update(id='persistent-identity')]:
            invalid = json.loads(json.dumps(payload))
            mutate(invalid['events'][0])
            assert client.post('/api/experience', json=invalid).status_code == 422
        assert client.post('/api/experience', content=b'x'*32769).status_code == 413
        response = client.post('/api/experience', json={'events': payload['events']*21})
        assert response.status_code == 422
        assert client.post('/api/experience?room=../../private', json=payload).status_code == 422
        for query in ['hours=999999', 'traffic=secret', 'room=bad', 'release=bad', 'scene=foo']:
            assert client.get('/api/experience?'+query).status_code == 422
    with TestClient(create_app(settings=settings)) as client:
        assert client.get('/api/experience?room=2').json()['samples'] == 1


@pytest.mark.parametrize('metric', ['stt_local_ms', 'action_ms'])
def test_nonfinite_metrics_rejected(metric):
    for value in [float('nan'), float('inf')]:
        with pytest.raises(ValueError):
            event(metrics={metric: value})


async def test_studio_first_actual_step_not_administrative_stop_and_no_replay(tmp_path):
    from duckking.mcp import DeviceMCP
    from duckking.motion import MotionController, PreviewBackend
    from duckking.studio import Studio
    motion = MotionController(PreviewBackend())
    studio = Studio(motion, tmp_path)
    motion.studio = studio
    await studio.select('director')
    mcp = DeviceMCP(motion, 'test')
    observed = []
    def observe(name, **fields):
        observed.append((name, fields, motion.current['name'] if motion.current else None))
    command = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
        'name': 'duck_direct', 'arguments': {'title': 'test', 'steps': [
            {'action': 'nod', 'duration': .2}, {'action': 'shake_head', 'duration': .2}]}}}
    try:
        result = await mcp.handle(command, observe=observe)
        assert not result['result']['isError']
        assert [(name, fields.get('result')) for name, fields, _ in observed] == [
            ('action_start', None), ('action_end', 'completed')]
        assert observed[0][2] == 'nod'
        await mcp.handle(command, observe=observe)
        assert len(observed) == 2
    finally:
        await motion.close()

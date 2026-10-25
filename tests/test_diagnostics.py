import json

from duckking.diagnostics import VoiceDiagnostics


def test_metadata_allowlist_capacity_and_private_rotating_files(tmp_path):
    path = tmp_path / "private" / "voice.jsonl"
    journal = VoiceDiagnostics(path, capacity=2, max_bytes=550)
    for _ in range(12):
        journal.record(
            "state", state="thinking", turn=1, uplink_frames=4,
            token="secret-token", device_id="private-device", text="private-transcript",
            method="secret-method", tool="secret-tool", elapsed_ms=-1, text_chars=True,
        )
    assert len(journal.snapshot()["events"]) == 2
    assert journal.sequence == 12
    assert journal.storage_ok
    files = list(path.parent.glob("voice.jsonl*"))
    assert len(files) == 2
    for file in files:
        assert file.stat().st_mode & 0o777 == 0o600
        assert file.stat().st_size <= 550
        text = file.read_text()
        assert "secret" not in text and "private" not in text
        for line in text.splitlines():
            entry = json.loads(line)
            assert entry["state"] == "thinking"
            assert entry["uplink_frames"] == 4
            assert "elapsed_ms" not in entry and "text_chars" not in entry
    memory = VoiceDiagnostics()
    memory.record("secret-event", state=[], turn=2**40)
    assert memory.snapshot()["events"][0]["event"] == "unknown"
    assert "secret" not in json.dumps(memory.snapshot())


def test_disk_failure_does_not_lose_in_memory_diagnostics_and_can_recover(tmp_path):
    parent = tmp_path / "blocked"
    parent.write_text("not a directory")
    journal = VoiceDiagnostics(parent / "voice.jsonl")
    journal.record("timeout", reason="response_idle")
    assert not journal.snapshot()["storage_ok"]
    assert journal.snapshot()["events"][0]["reason"] == "response_idle"
    parent.unlink()
    journal.record("state", state="ready")
    assert journal.storage_ok
    assert journal.path.is_file()


def test_stt_logging_redacts_known_secrets_and_identifiers_before_truncation(tmp_path):
    journal = VoiceDiagnostics(tmp_path / "voice.jsonl")
    text = (
        '向前走再向左转再向右转\n"文本" '
        'actual-secret 12:34:56:78:90:ab 12345678-1234-1234-1234-123456789abc '
        'token=unknown-secret Bearer another-secret https://example.com/key?x=secret'
    )
    journal.record("stt", text=text, sensitive_values={"actual-secret"}, text_chars=len(text))
    entry = journal.snapshot()["events"][0]
    assert entry["text"].startswith('向前走再向左转再向右转\n"文本"')
    assert entry["text_chars"] == len(text)
    assert "secret" not in entry["text"] and "12:34" not in entry["text"]
    assert "12345678" not in entry["text"] and "https" not in entry["text"]
    assert len(journal.path.read_text().splitlines()) == 1
    journal.record("stt", text="长" * 1998 + "actual-secret", sensitive_values={"actual-secret"})
    assert len(journal.events[-1]["text"]) == 2000
    assert "actual" not in journal.events[-1]["text"]
    journal.record("stt", text=[])
    assert journal.events[-1]["text"] == ""
    journal.record("tts_sentence", text="回复不落盘")
    assert "text" not in journal.events[-1]
    assert [journal.next_turn(), journal.next_turn()] == [1, 2]

def test_browser_audio_is_allowlisted_throttled_and_separate_from_cloud(tmp_path, monkeypatch):
    import pytest

    now = [100.0]
    monkeypatch.setattr('duckking.diagnostics.time.monotonic', lambda: now[0])
    journal = VoiceDiagnostics(tmp_path / 'voice.jsonl')
    journal.update_playback({
        'output_state': 'interrupted', 'received_frames': 10, 'scheduled_frames': 0,
        'queued_ms': 600, 'signal_peak_milli': 200, 'ended_frames': True,
        'dropped_frames': -1, 'output_sample_rate': 2**40,
        'token': 'secret', 'text': 'private', 'user_agent': 'private-device',
    })
    assert journal.playback == {
        'output_state': 'interrupted', 'received_frames': 10, 'scheduled_frames': 0,
        'queued_ms': 600, 'signal_peak_milli': 200,
    }
    journal.update_playback({'output_state': 'interrupted', 'received_frames': 11})
    assert len(journal.events) == 1 and journal.playback['received_frames'] == 11
    now[0] += 1
    journal.update_playback({'output_state': 'interrupted', 'received_frames': 12})
    journal.update_playback({'output_state': 'running', 'ended_frames': 12})
    assert len(journal.events) == 3
    assert all(event['event'] == 'browser_audio' for event in journal.events)
    for state in [[], {}, None, 'secret']:
        with pytest.raises(ValueError):
            journal.update_playback({'output_state': state})
    assert journal.snapshot()['browser_audio']['output_state'] == 'running'
    text = journal.path.read_text() + json.dumps(journal.snapshot())
    assert 'secret' not in text and 'private' not in text

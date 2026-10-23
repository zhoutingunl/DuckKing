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

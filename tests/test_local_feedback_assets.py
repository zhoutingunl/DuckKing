"""Shipped local confirmations must be short, audible and independently labelled."""

import array
import hashlib
import json
import wave
from pathlib import Path


def test_local_feedback_audio_matches_disclosed_manifest():
    folder = Path(__file__).resolve().parents[1] / "frontend/public/local-feedback"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert "prerecorded local feedback" in manifest["source"]
    assert {line["id"] for line in manifest["lines"]} == {"completed", "failed"}
    for line in manifest["lines"]:
        path = folder / (line["id"] + ".wav")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == line["sha256"]
        with wave.open(str(path)) as audio:
            assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (
                1, 2, 16000,
            )
            assert 0 < audio.getnframes() / audio.getframerate() <= 5
            samples = array.array("h", audio.readframes(audio.getnframes()))
        assert max(abs(sample) for sample in samples) > 1000

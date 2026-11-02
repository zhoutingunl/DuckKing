"""Media regression: mono narration must survive a stereo recording between chapters."""

import importlib.util
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="Demo audio composition needs FFmpeg and ffprobe",
)


@pytest.mark.parametrize("gapped", [False, True])
def test_mono_stereo_mono_join_preserves_audio_and_silent_tails(tmp_path, gapped):
    path = Path(__file__).resolve().parents[1] / "scripts/build_current_demo.py"
    spec = importlib.util.spec_from_file_location("build_current_demo", path)
    composer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(composer)
    parts = []
    seconds = 1.24  # Deliberately not an integer number of AAC frames.
    for i, (rate, frequencies) in enumerate([(24000, [1000]), (48000, [440, 880]),
                                             (24000, [1500])]):
        time = np.arange(round(rate * seconds)) / rate
        envelope = ((time >= 0.15) & (time < 0.85)) * 0.2
        pcm = np.stack([np.sin(2 * np.pi * f * time) * envelope for f in frequencies], axis=1)
        wav = tmp_path / f"{i}.wav"
        with wave.open(str(wav), "wb") as audio:
            audio.setparams((len(frequencies), 2, rate, 0, "NONE", "not compressed"))
            audio.writeframes((pcm * 32767).astype("<i2").tobytes())
        part = tmp_path / f"{i}.mp4"
        gap = ["-af", "aselect='not(between(t,0.35,0.50))'"] if gapped and i == 1 else []
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"color=black:size=160x100:rate=25:duration={seconds}", "-i", str(wav),
            "-vf", f"setsar={'10/11' if i == 1 else '1/1'}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
            *gap, "-t", str(seconds), str(part),
        ], check=True)
        parts.append(part)
    output = tmp_path / "joined.mp4"
    composer.concatenate_parts(parts, output)

    def decode(file):
        raw = subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", str(file), "-map", "0:a:0", "-ac", "2",
            "-af", "aresample=48000:async=1:first_pts=0", "-f", "f32le", "pipe:1",
        ])
        return np.frombuffer(raw, dtype="<f4").reshape(-1, 2)

    result = decode(output)
    for i, part in enumerate(parts):
        expected = decode(part)
        start = round(i * seconds * 48000)
        actual = result[start:start + len(expected)]
        # Check each channel: a mono downmix would lose the independent stereo tones.
        begin, end = round(0.25 * 48000), round(0.65 * 48000)
        for channel in range(2):
            correlation = np.corrcoef(expected[begin:end, channel], actual[begin:end, channel])
            assert correlation[0, 1] > 0.99, (i, channel, correlation[0, 1])
        quiet = actual[round(0.95 * 48000):round(1.18 * 48000)]
        assert np.sqrt(np.mean(quiet ** 2)) < 10 ** (-65 / 20), i
    assert composer.duration(output) == pytest.approx(3 * seconds, abs=0.04)

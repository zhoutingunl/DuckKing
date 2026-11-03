"""Build two disclosed local confirmations; runtime never needs cloud TTS or macOS."""

import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = "Eddy (中文（中国大陆）)"
LINES = {"completed": "完成啦，嘎。", "failed": "这次没完成，请再试一次。"}


def main():
    output = ROOT / "frontend/public/local-feedback"
    output.mkdir(exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "voice.aiff"
        for name, text in LINES.items():
            subprocess.run(["say", "-v", VOICE, "-r", "210", "-o", str(source), text],
                           check=True)
            rate = int(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                "-of", "csv=p=0", str(source),
            ], text=True).strip())
            target = output / f"{name}.wav"
            subprocess.run([
                "ffmpeg", "-v", "error", "-y", "-i", str(source), "-af",
                f"asetrate={rate * 1.14},aresample=22050,atempo=0.877193,"
                "highpass=f=170,lowpass=f=6500,tremolo=f=7:d=0.08",
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(target),
            ], check=True)
            with wave.open(str(target)) as audio:
                seconds = audio.getnframes() / audio.getframerate()
            assert 0 < seconds <= 5
            records.append({"id": name, "text": text, "seconds": round(seconds, 3),
                            "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (output / "manifest.json").write_text(json.dumps({
        "source": "macOS synthetic voice; prerecorded local feedback, not Linx or voice cloning",
        "voice": VOICE, "rate": 210, "processing": "pitch +14%, light tremolo",
        "sample_rate": 16000, "channels": 1, "lines": records,
    }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

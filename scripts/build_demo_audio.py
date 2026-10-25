"""Generate disclosed prerecorded Chinese theatre speech using macOS Tingting.

Runtime needs neither macOS nor a microphone. No voice cloning or cloud TTS is implied.
"""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = subprocess.check_output(
        ["node", "--input-type=module", "-e",
         "import {AUDIO_LINES} from './frontend/src/demo-catalog.js';"
         "process.stdout.write(JSON.stringify(AUDIO_LINES));"], cwd=ROOT, text=True,
    )
    lines = json.loads(source)
    output = ROOT / "frontend/public/demo-audio"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        for line in lines:
            text = Path(temp) / "line.txt"
            text.write_text(line["text"])
            wav = Path(temp) / "speech.aiff"
            subprocess.run(["say", "-v", "Tingting", "-r", "205", "-f", str(text),
                            "-o", str(wav)], check=True)
            target = output / (line["id"] + ".wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ar", "16000",
                            "-ac", "1", "-c:a", "pcm_s16le", str(target)], check=True)
            line["bytes"] = target.stat().st_size
    (output / "manifest.json").write_text(json.dumps(
        {"source": "macOS Tingting, prerecorded synthetic speech", "sample_rate": 16000,
         "lines": lines}, ensure_ascii=False, indent=2) + "\n")
    print(f"Generated {len(lines)} prerecorded lines")


if __name__ == "__main__":
    main()

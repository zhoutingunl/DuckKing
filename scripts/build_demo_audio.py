"""Generate disclosed prerecorded speech with distinct human and duck personas.

Runtime needs neither macOS nor a microphone. No voice cloning or cloud TTS is implied.
"""

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICES = {
    "预录指令": ("Tingting", 205, "human"),
    "旁白": ("Tingting", 185, "narrator"),
    "鸭子": ("Eddy (中文（中国大陆）)", 210, "duck"),
}


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
            voice, rate, persona = VOICES[line["role"]]
            text = Path(temp) / "line.txt"
            text.write_text(line["text"])
            wav = Path(temp) / "speech.aiff"
            subprocess.run(["say", "-v", voice, "-r", str(rate), "-f", str(text),
                            "-o", str(wav)], check=True)
            target = output / (line["id"] + ".wav")
            filters = []
            if persona == "duck":
                sample_rate = int(subprocess.check_output([
                    "ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                    "-of", "csv=p=0", str(wav),
                ], text=True).strip())
                filters = ["-af", f"asetrate={sample_rate * 1.14},aresample=22050,"
                           "atempo=0.877193,highpass=f=170,lowpass=f=6500,tremolo=f=7:d=0.08"]
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), *filters, "-ar", "16000",
                            "-ac", "1", "-c:a", "pcm_s16le", str(target)], check=True)
            line["bytes"] = target.stat().st_size
            line.update(voice=voice, persona=persona, rate=rate,
                        processing="pitch +14%, light tremolo" if persona == "duck" else "none")
    (output / "manifest.json").write_text(json.dumps(
        {"source": "macOS synthetic voices, distinct human / duck personas", "sample_rate": 16000,
         "lines": lines}, ensure_ascii=False, indent=2) + "\n")
    print(f"Generated {len(lines)} prerecorded lines")


if __name__ == "__main__":
    main()

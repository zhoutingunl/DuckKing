"""Create disclosed nasal/raspy synthetic speech for audition, not a trained clone."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE = "Eddy (中文（中国大陆）)"
TEXT = (
    "你好，我是鸭王。别看我个子小，听到的任务我会认真记住。"
    "现在请你当导演，说说想让我怎么演。向左看，向右看，点点头，慢慢坐下。"
    "如果你改变主意，就告诉我暂停。我会先站稳，等你说完，再继续。"
    "小棒放稳了才算送到，球真的踢中了才算进步。今天也一起加油吧。"
)
STYLES = {
    "nasal": ("轻鼻音 · 清晰优先", "highpass=f=180,equalizer=f=1000:t=q:w=1.5:g=4,"
              "equalizer=f=2300:t=q:w=1.8:g=2,lowpass=f=6800,tremolo=f=24:d=0.05"),
    "raspy": ("轻沙哑＋鼻音 · 推荐", "highpass=f=190,equalizer=f=1050:t=q:w=1.5:g=5,"
              "equalizer=f=2600:t=q:w=2:g=2,volume=1.5,asoftclip=type=tanh:threshold=0.65,"
              "tremolo=f=30:d=0.10,lowpass=f=6400"),
    "strong": ("鼻音更重 · 对照", "highpass=f=240,equalizer=f=1150:t=q:w=1.8:g=7,"
               "equalizer=f=2300:t=q:w=2:g=3,volume=1.6,asoftclip=type=tanh:threshold=0.6,"
               "tremolo=f=35:d=0.13,lowpass=f=5600"),
}


def main():
    output = ROOT / "frontend/public/voice-samples"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"source": "macOS Eddy Chinese synthetic speech, offline DSP; not a clone",
                "voice": VOICE, "text": TEXT, "samples": []}
    with tempfile.TemporaryDirectory() as temp:
        raw = Path(temp) / "source.aiff"
        text = Path(temp) / "text.txt"
        text.write_text(TEXT)
        subprocess.run(["say", "-v", VOICE, "-r", "225", "-f", str(text), "-o", str(raw)],
                       check=True)
        for key, (label, filters) in STYLES.items():
            target = output / f"{key}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                            filters + ",loudnorm=I=-18:TP=-2:LRA=7", "-ar", "24000",
                            "-ac", "1", "-c:a", "pcm_s16le", str(target)], check=True)
            duration = float(subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", str(target)], text=True).strip())
            manifest["samples"].append({"key": key, "label": label, "file": target.name,
                "duration_s": duration, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "processing": filters})
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"samples": [{"key": s["key"], "duration_s": s["duration_s"]}
                                   for s in manifest["samples"]]}))


if __name__ == "__main__":
    main()

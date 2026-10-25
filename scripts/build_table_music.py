"""Prepare the user's supplied recordings for a 36-second tabletop performance.

The four layers are an octave/chorus treatment of a supplied mix, not isolated
vocals or newly recorded singers. No song is downloaded by this script.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(source, target, filters, channels=2):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            filters,
            "-t",
            "36",
            "-ar",
            "44100",
            "-ac",
            str(channels),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(target),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vocal", type=Path, required=True)
    parser.add_argument("--instrumental", type=Path, required=True)
    args = parser.parse_args()
    output = ROOT / "frontend/public/demo-music"
    output.mkdir(exist_ok=True)
    normalize = (
        "atrim=0:36,asetpts=PTS-STARTPTS,apad=whole_dur=36,atrim=0:36,"
        "loudnorm=I=-18:TP=-2:LRA=9,aresample=44100"
    )
    fade = "afade=t=in:d=0.08,afade=t=out:st=35.1:d=0.9"
    mono = "pan=mono|c0=0.5*c0+0.5*c1"
    layers = {
        "a": (
            f"{mono},asetrate=22050,aresample=44100,atempo=2,lowpass=f=900,"
            "highpass=f=60,volume=.10",
            1,
            "octave below, quiet low-pass layer",
        ),
        "b": (
            f"{mono},chorus=.6:.8:12:0.25:.3:1,highpass=f=170,lowpass=f=3500,volume=.12",
            1,
            "unison chorus layer",
        ),
        "c": ("volume=.85", 2, "original lead mix"),
        "d": (
            f"{mono},asetrate=88200,aresample=44100,atempo=.5,highpass=f=800,"
            "lowpass=f=5000,volume=.08",
            1,
            "octave above, quiet high-pass layer",
        ),
    }
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp) / "normalized.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(args.vocal),
                "-af",
                normalize,
                "-ar",
                "44100",
                "-ac",
                "2",
                str(base),
            ],
            check=True,
        )
        render(base, output / "night-star-vocal.mp3", fade)
        for part, (filters, channels, _) in layers.items():
            render(
                base,
                output / f"night-star-{part}.mp3",
                filters + ",apad=whole_dur=36,atrim=0:36," + fade,
                channels,
            )
        render(args.instrumental, output / "night-star-instrumental.mp3", normalize + "," + fade)
    metadata = {
        "title": "夜空中最亮的星",
        "source": "user_provided_recordings",
        "rights": (
            "User-supplied music; original rights retained. "
            "Not covered by the repository MIT license."
        ),
        "duration": 36,
        "source_offset_seconds": 0,
        "vocal_sha256": hashlib.sha256(args.vocal.read_bytes()).hexdigest(),
        "instrumental_sha256": hashlib.sha256(args.instrumental.read_bytes()).hexdigest(),
        "layers": {k: v[2] for k, v in layers.items()},
        "limitation": (
            "Processed original mix, including its accompaniment; "
            "not isolated vocal stems or independent SATB arrangements."
        ),
        "files": {
            p.name: {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(output.glob("*.mp3"))
        },
    }
    (output / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print("Prepared supplied vocal mix, four gentle layers, and instrumental alternative")


if __name__ == "__main__":
    main()

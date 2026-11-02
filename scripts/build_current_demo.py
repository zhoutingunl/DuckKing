"""Compose actual browser recordings with disclosed narration and chapter labels."""

import argparse
import concurrent.futures
import hashlib
import json
import math
import shutil
import subprocess
import wave
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def duration(path):
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
    )


def concatenate_parts(parts, output):
    """Decode each chapter separately before joining different AAC layouts.

    The concat demuxer reuses the first stream's codec configuration. Passing
    mono narration and stereo page audio through it can corrupt the narration
    after the stereo chapter without reporting a decoder error.
    """
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    filters, streams = [], []
    for i, part in enumerate(parts):
        command += ["-i", str(part)]
        filters += [
            f"[{i}:v]fps=25,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{i}]",
            f"[{i}:a]aresample=48000:async=1:first_pts=0,"
            "aformat=channel_layouts=stereo,apad,"
            f"atrim=duration={duration(part)},asetpts=PTS-STARTPTS[a{i}]",
        ]
        streams += [f"[v{i}][a{i}]"]
    filters += ["".join(streams) + f"concat=n={len(parts)}:v=1:a=1[video][audio]"]
    run(
        command
        + [
            "-filter_complex", ";".join(filters),
            "-map", "[video]", "-map", "[audio]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", "25",
            "-preset", "veryfast", "-crf", "24",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
            "-movflags", "+faststart", str(output),
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--script", type=Path, default=Path("docs/media/current-demo-script.json"))
    parser.add_argument("--work", type=Path, default=Path(".duckking/current-demo-edit"))
    parser.add_argument("--output", type=Path, default=Path("docs/media/duckking-current-demo.mp4"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    proof = json.loads(args.recording.read_text())
    if not proof.get("completed") or proof["page_errors"]:
        raise ValueError("Recording must complete without page errors; inspect evidence first")
    if proof.get("validation_type") == "live_tabletop":
        table = next(c for c in proof["chapters"] if c["id"] == "tabletop")
        if table["result"]["mode"] != "live_linx" or not table["result"]["cloud_audio_frames"]:
            raise ValueError("Missing real cloud response")
        sync = table.get("sync_evidence")
        if not sync or max(abs(sync[k]) for k in ["start_delta_ms", "end_delta_ms"]) > 350:
            raise ValueError("Page audio must pass actual output-clock and physics synchronization")
        if not any(
            a["tool"] == "duck_table_show" and a["result"] == "completed"
            for r in proof["new_rounds"]
            for a in r["actions"]
        ):
            raise ValueError("Missing real table tool result in statistics")
        if len(proof["new_rounds"]) < 2 or any(
            r["status"] != "completed" for r in proof["new_rounds"]
        ):
            raise ValueError("An actual cloud round timed out or did not finish")
        if not any(
            e["event"] == "tool_end"
            and e.get("tool") == "duck_get_status"
            and e.get("result") == "ok"
            for e in proof["cloud_tool_events"]
        ):
            raise ValueError("Missing real status query")
    else:
        balance = next(c for c in proof["chapters"] if c["id"] == "balance")
        for name, expected_seconds in [("standard", 13), ("custom", 30)]:
            state = balance[name]
            if state["duration_seconds"] != expected_seconds:
                raise ValueError(f"{name} has the wrong challenge duration")
            for side in [state, state["comparison"]["baseline"]]:
                if side["phase"] not in {"completed", "failed"} or not side.get("result"):
                    raise ValueError(f"{name} still has an unfinished side")
    script = json.loads(args.script.read_text())
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    beijing_date = (
        datetime.fromisoformat(proof["recorded_at"])
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .strftime("%Y-%m-%d")
    )
    release = proof.get("release")
    version = release["commit"][:7] if release else proof["source_commit"][:7]
    location = "线上" if release else "本地候选版本"
    identity = f"{beijing_date}（北京时间） · {location} {version}"
    if script.get("identity_note"):
        identity = f"{beijing_date}（北京时间） · {script['identity_note']}"
    run(
        [
            "node",
            str(root / "frontend/scripts/render-demo-cards.mjs"),
            str(args.script.resolve()),
            str(args.work.resolve()),
            identity,
        ]
    )

    def narrate(item):
        i, chapter = item
        if chapter.get("audio") == "silent":
            target = args.work / f"{i}-silence.wav"
            with wave.open(str(target), "wb") as silent:
                silent.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
                silent.writeframes(bytes(round(chapter["duration_seconds"] * 48000) * 4))
            return target, "Intentional silent closing card; no narration"
        if chapter.get("audio") == "page":
            original = next(c for c in proof["chapters"] if c["id"] == chapter["id"])
            if len(original.get("audio", [])) != 1:
                raise ValueError("Expected exactly one captured page audio context")
            return Path(original["audio"][0]["file"]), "Captured actual browser playback"
        target = args.work / f"{i}.mp3"
        text = args.work / f"{i}.txt"
        text.write_text(chapter["narration"])
        provider = f"Microsoft Edge TTS / {script['voice']} / edge-tts 7.3.1"
        if not target.exists():
            try:
                run(
                    [
                        "uvx",
                        "--from",
                        "edge-tts==7.3.1",
                        "edge-tts",
                        "--voice",
                        script["voice"],
                        f"--rate={script['rate']}",
                        "--file",
                        str(text),
                        "--write-media",
                        str(target),
                    ],
                    timeout=60,
                )
            except (subprocess.SubprocessError, OSError):
                if not shutil.which("say"):
                    raise
                provider = "macOS say / Tingting"
                aiff = args.work / f"{i}.aiff"
                run(["say", "-v", "Tingting", "-r", "190", "-f", str(text), "-o", str(aiff)])
                run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff), str(target)])
        provider_file = args.work / f"{i}-voice.json"
        if provider_file.exists():
            provider = json.loads(provider_file.read_text())["provider"]
        provider_file.write_text(json.dumps({"provider": provider}, ensure_ascii=False))
        return target, provider

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        voices = list(pool.map(narrate, enumerate(script["chapters"])))
    entries, elapsed = [], 0.0
    for i, (c, (voice, provider)) in enumerate(zip(script["chapters"], voices, strict=True)):
        card = args.work / f"{i}.png"
        part = args.work / f"part-{i}.mp4"
        # MediaRecorder's streaming WebM audio need not contain a duration header.
        # The captured performance is bounded by its recorded video segment.
        audio_duration = 0.0 if c.get("audio") == "page" else duration(voice)
        source, start, original_seconds, clock_offset = None, 0.0, 0.0, 0.0
        if c.get("segment"):
            chapter = next(x for x in proof["chapters"] if x["id"] == c["id"])
            segment = next(x for x in chapter["segments"] if x["name"] == c["segment"])
            if segment["status"] != "completed":
                raise ValueError("Cannot publish an incomplete segment as completed")
            source = Path(chapter["video"])
            # Screencast timestamps can start after the page's wall clock.
            # Anchor the final retained frame; this is editorial alignment,
            # never a measurement of browser/audio/physics latency.
            raw_seconds = duration(source)
            clock_offset = chapter.get(
                "video_start_elapsed_seconds", chapter["segments"][-1]["end_seconds"] - raw_seconds
            )
            start = max(0, segment["start_seconds"] - clock_offset)
            end = min(raw_seconds, segment["end_seconds"] - clock_offset)
            start += c.get("source_trim_start_seconds", 0)
            end -= c.get("source_trim_end_seconds", 0)
            if end <= start:
                raise ValueError("Chapter trimming removed its entire source segment")
            original_seconds = end - start
        page_audio = c.get("audio") == "page"
        seconds = (
            math.ceil(
                (original_seconds if page_audio else max(original_seconds, audio_duration + 1.0))
                * 25
            )
            / 25
        )
        if c.get("audio") == "silent":
            seconds = c["duration_seconds"]
        audio_filter = "loudnorm=I=-18:TP=-2:LRA=9,apad"
        if page_audio:
            audio = chapter["audio"][0]
            offset = audio["started_elapsed_seconds"] - clock_offset - start
            trim = max(0, -offset)
            delay = round(max(0, offset) * 1000)
            audio_filter = f"atrim=start={trim},asetpts=PTS-STARTPTS,adelay={delay}:all=1,apad"
        if source:
            command = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                str(start),
                "-t",
                str(original_seconds),
                "-i",
                str(source),
                "-loop",
                "1",
                "-i",
                str(card),
                "-i",
                str(voice),
                "-filter_complex",
                "[0:v]fps=25:start_time=0,setpts=PTS-STARTPTS,"
                "scale=1600:1000:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "pad=1600:1100:0:0:color=0x182226,"
                f"tpad=stop_mode=clone:stop_duration={seconds},trim=duration={seconds}[v];"
                f"[v][1:v]overlay=0:0:shortest=1[out];[2:a]{audio_filter}[a]",
            ]
        else:
            command = [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(card),
                "-i",
                str(voice),
                "-filter_complex",
                "[0:v]fps=25[out];[1:a]loudnorm=I=-18:TP=-2:LRA=9,apad[a]",
            ]
        run(
            command
            + [
                "-map",
                "[out]",
                "-map",
                "[a]",
                "-t",
                str(seconds),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(part),
            ]
        )
        actual_seconds = duration(part)
        entries.append(
            {
                **c,
                "start_seconds": elapsed,
                "duration_seconds": actual_seconds,
                "source_video": source.name if source else None,
                "source_start_seconds": start,
                "source_clock_offset_seconds": clock_offset,
                "source_seconds": original_seconds,
                "end_hold_seconds": max(0, seconds - original_seconds) if source else 0,
                "voice_provider": provider,
                **({"provenance": chapter["provenance"]}
                   if c.get("segment") and chapter.get("provenance") else {}),
            }
        )
        elapsed += actual_seconds
        print(f"Encoded {i + 1}/{len(voices)}: {c['title']}", flush=True)
    temporary_output = args.output.with_name(args.output.stem + ".building" + args.output.suffix)
    concatenate_parts([args.work / f"part-{i}.mp4" for i in range(len(entries))], temporary_output)
    run(["ffmpeg", "-v", "error", "-i", str(temporary_output), "-f", "null", "-"])
    temporary_output.replace(args.output)
    manifest = {
        "release": proof["release"],
        "recorded_at": proof["recorded_at"],
        "edited_at": proof.get("edited_at"),
        "base_url": proof["base_url"],
        "source": proof["source"],
        "audio": proof.get(
            "audio", "Actual page audio in the performance; synthetic chapter narration"
        ),
        "audio_encoding": {
            "codec": "AAC",
            "sample_rate_hz": 48000,
            "channels": 2,
            "joining": "Chapters decoded separately, normalized to stereo PCM, then concatenated",
        },
        "source_commit": proof.get("source_commit"),
        "duration_seconds": duration(args.output),
        "chapters": entries,
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "editing": (
            "Loading waits omitted between marked segments; all action footage at original "
            "wall-clock speed. Source trims and end holds are disclosed per chapter. "
            "Captions occupy a "
            "separate 100 px band; source frames are scaled to fit 1600x1000, "
            "with recorded app state and displayed values preserved."
        ),
        "validation": "ffmpeg full video/audio decode passed",
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    # Publish screenshots and evidence without machine-specific paths.
    public_proof = json.loads(json.dumps(proof))
    for chapter in public_proof["chapters"]:
        raw = Path(chapter["video"])
        chapter["video_sha256"] = hashlib.sha256(raw.read_bytes()).hexdigest()
        chapter["video"] = raw.name
        for audio in chapter.get("audio", []):
            source = Path(audio["file"])
            audio["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            audio["file"] = source.name
        for screenshot in chapter["screenshots"]:
            source = Path(screenshot["file"])
            shutil.copyfile(source, args.output.parent / source.name)
            screenshot["file"] = source.name
            screenshot["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    evidence_name = (
        "current-demo-recording.json"
        if args.output.stem == "duckking-current-demo"
        else args.output.stem + "-recording.json"
    )
    (args.output.parent / evidence_name).write_text(
        json.dumps(public_proof, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()

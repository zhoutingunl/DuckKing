"""Combine actual recordings while retaining each chapter's version and evidence."""

import argparse
import copy
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def read_recording(path):
    data = json.loads(path.read_text())
    if not data.get("completed") or data.get("page_errors"):
        raise ValueError(f"Recording did not pass: {path}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--supplements", type=Path, required=True)
    parser.add_argument("--tour", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    live, supplements, tour = map(read_recording, [args.live, args.supplements, args.tour])
    local = next(c for c in supplements["chapters"] if c["id"] == "local_asr")
    rounds = local["rounds"]
    if len(rounds) != 1 or rounds[0]["route"] != "local" or rounds[0]["status"] != "completed":
        raise ValueError("Missing real local-only recognition result")
    if rounds[0]["uplink_frames"] or rounds[0]["downlink_frames"]:
        raise ValueError("Local-only example unexpectedly used cloud audio")
    if [a["tool"] for a in rounds[0]["actions"]] != ["duck_roulade", "duck_yawn"] or any(
        a["result"] != "completed" for a in rounds[0]["actions"]
    ):
        raise ValueError("The two local physical actions did not complete")
    training = next(c for c in supplements["chapters"] if c["id"] == "training")["training"]
    if training["run"] != "level2-cpu-v4" or "89/100" not in training["gate"]:
        raise ValueError("The selected level-two training record has not actually rendered")
    coverage = next(c for c in supplements["chapters"] if c["id"] == "coverage")
    deployment = coverage["deployment"]
    if deployment["coverage"]["commit"] != deployment["commit"]:
        raise ValueError("Coverage belongs to another commit")
    for key in ["lines", "branches"]:
        counts = deployment["coverage"][key]
        if not 0 <= counts["covered"] <= counts["total"] or counts["total"] <= 0:
            raise ValueError("Invalid coverage counts")
    result = copy.deepcopy(live)
    result["edited_at"] = datetime.now(UTC).isoformat()
    result["source"] = (
        "Actual Linx STT/MCP/TTS performance; actual offline SenseVoice and MuJoCo; "
        "public balance comparison, saved CPU training and commit-bound coverage. "
        "Separate recordings and versions are retained per chapter."
    )
    for chapter in result["chapters"]:
        chapter["provenance"] = {
            "recorded_at": live["recorded_at"], "base_url": live["base_url"],
            "source_commit": live["source_commit"], "release": live["release"],
            "source": live["source"],
        }
    result["chapters"] += copy.deepcopy(supplements["chapters"])
    balance = copy.deepcopy(next(c for c in tour["chapters"] if c["id"] == "balance"))
    # Keep the full source recording's clock anchor before selecting its first
    # segment; otherwise the later 30-second trial would be mistaken for 13 seconds.
    raw_duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", balance["video"],
    ]))
    balance["video_start_elapsed_seconds"] = (
        balance["segments"][-1]["end_seconds"] - raw_duration
    )
    balance["capture_clock_source"] = "Original final-marker alignment retained before trimming"
    for state in [balance["standard"], balance["standard"]["comparison"]["baseline"]]:
        if state["phase"] not in {"completed", "failed"} or not state.get("result"):
            raise ValueError("Balance comparison was not actually finished")
    balance["segments"] = [
        s for s in balance["segments"] if s["name"] == "paired-standard-13-seconds"
    ]
    balance.pop("custom", None)
    balance.pop("training", None)
    balance["screenshots"] = [
        s for s in balance["screenshots"]
        if Path(s["file"]).name in {"current-balance-running.png", "current-balance-result.png"}
    ]
    balance["provenance"] = {
        "recorded_at": tour["recorded_at"], "base_url": tour["base_url"],
        "source_commit": tour["release"]["commit"], "release": tour["release"],
        "source": tour["source"],
    }
    result["chapters"].append(balance)
    result["editorial"] = {
        "previous_video_duration_seconds": 177.6,
        "measured_silent_interval_seconds": [92.451604, 106.069917],
        "removed_redundant_wait_seconds": [93.0, 105.88],
        "note": "Keep the spoken ending and a short pause; omit the following wait.",
        "closing_card": "Three seconds, intentionally without narration",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

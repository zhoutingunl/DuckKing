"""Bounded, process-local voice measurements; no inferred physical or acoustic timing."""

import math
from collections import Counter, deque
from datetime import UTC, datetime


def distribution(values):
    """Nearest-rank percentiles. Missing and unfinished samples are never zero-filled."""
    values = sorted(values)
    return {
        "count": len(values),
        "p50_ms": values[math.ceil(len(values) * .50) - 1] if values else None,
        "p95_ms": values[math.ceil(len(values) * .95) - 1] if values else None,
    }


class VoiceStatistics:
    def __init__(self, capacity=500):
        self.rounds = deque(maxlen=capacity)
        self.started_at = datetime.now(UTC).isoformat(timespec="seconds")
        self.total_rounds = 0
        self.service = {kind: Counter() for kind in ("preview", "robotd")}
        self.recovering = {}
        self.recoveries = {kind: deque(maxlen=capacity) for kind in self.service}

    def observe(self, entry, clock):
        backend = entry.get("backend")
        if backend not in self.service:
            return
        event, state = entry["event"], entry.get("state")
        counts = self.service[backend]
        if event in {"connection_error", "command_error", "reset", "timeout"}:
            counts[event] += 1
        if event == "state":
            if state == "recovering":
                counts["reconnect_attempts"] += 1
                self.recovering[backend] = clock
            elif state == "ready" and backend in self.recovering:
                counts["reconnect_successes"] += 1
                elapsed = round((clock - self.recovering.pop(backend)) * 1000)
                self.recoveries[backend].append(elapsed)
            elif state in {"disconnected", "error", "connecting"}:
                self.recovering.pop(backend, None)
        turn = entry.get("turn", 0)
        if event == "listen_start":
            self.total_rounds += 1
            self.rounds.append({
                "turn": turn, "time": entry["time"], "backend": backend,
                "status": "listening", "text": "", "timings": {}, "actions": [],
                "uplink_frames": 0, "downlink_frames": 0,
            })
        row = next((row for row in reversed(self.rounds) if row["turn"] == turn), None)
        if row is None:
            return  # Unsolicited greetings / tool discovery are not user rounds.
        elapsed = entry.get("elapsed_ms", 0)
        for key in ("uplink_frames", "downlink_frames"):
            row[key] = max(row[key], entry.get(key, 0))
        terminal = row["status"] in {"completed", "timeout", "interrupted", "error"}
        if event == "action_end":
            action = next((a for a in row["actions"] if a["call"] == entry.get("call")), None)
            if action is not None and action["result"] == "running":
                action.update(result=entry["result"], duration_ms=max(0, elapsed - action["at_ms"]))
            return
        if terminal:
            return
        timings = row["timings"]
        if event == "listen_stop":
            timings.setdefault("listen_stop", elapsed)
            row["status"] = "waiting"
        elif event == "stt":
            row["text"] = entry.get("text", "")
            if row["text"].strip():
                timings.setdefault("stt", elapsed)
        elif event == "action_start":
            row["actions"].append({
                "call": entry["call"], "tool": entry["tool"], "at_ms": elapsed,
                "result": "running", "duration_ms": None,
            })
            timings.setdefault("action_start", elapsed)
        elif event == "downlink_first_frame":
            timings.setdefault("first_audio", elapsed)
        elif event == "tts_stop":
            timings["reply_end"] = elapsed
            row["status"] = "completed" if entry.get("result") == "ok" else "interrupted"
        elif event == "timeout" and entry.get("reason") != "recording_limit":
            row.update(status="timeout", reason=entry.get("reason"))
        elif event in {"connection_error", "command_error"}:
            row["status"] = "error"
        elif event == "reset" or (event == "state" and state == "disconnected"):
            row["status"] = "interrupted"

    def snapshot(self, backend=None):
        rows = [r for r in self.rounds if backend is None or r["backend"] == backend]
        submitted = [r for r in rows if "listen_stop" in r["timings"]]
        closed = [r for r in submitted if r["status"] not in {"listening", "waiting"}]
        latencies = {}
        for name in ("stt", "action_start", "first_audio", "reply_end"):
            latencies[name] = distribution([
                r["timings"][name] - r["timings"]["listen_stop"] for r in submitted
                if name in r["timings"] and r["timings"][name] >= r["timings"]["listen_stop"]
            ])
        actions = [a for r in rows for a in r["actions"]]
        finished_actions = [a for a in actions if a["result"] != "running"]
        latencies["action_duration"] = distribution([
            a["duration_ms"] for a in finished_actions if a["duration_ms"] is not None
        ])
        kinds = [backend] if backend else list(self.service)
        counts = sum((self.service[k] for k in kinds), Counter())
        latencies["recovery"] = distribution([v for k in kinds for v in self.recoveries[k]])
        return {
            "started_at": self.started_at, "capacity": self.rounds.maxlen,
            "total_rounds": self.total_rounds, "backend": backend or "all",
            "counts": {
                "rounds": len(rows), "submitted": len(submitted), "closed": len(closed),
                "pending": sum(r["status"] in {"listening", "waiting"} for r in rows),
                "recognized": sum("stt" in r["timings"] for r in closed),
                "replied": sum(r["status"] == "completed" for r in closed),
                "timeouts": sum(r["status"] == "timeout" for r in rows),
                "interrupted": sum(r["status"] == "interrupted" for r in rows),
                "errors": sum(r["status"] == "error" for r in rows),
                "actions": len(actions), "finished_actions": len(finished_actions),
                "completed_actions": sum(a["result"] == "completed" for a in finished_actions),
            },
            "service": dict(counts), "latencies": latencies,
            "rounds": list(reversed(rows)),
        }

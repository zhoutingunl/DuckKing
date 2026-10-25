"""Private bounded journal with redacted STT; no audio, device IDs, or credentials."""

import json
import os
import re
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from .statistics import VoiceStatistics

STATES = {
    "disconnected", "connecting", "recovering", "interrupting", "awaiting_binding", "ready",
    "listening", "thinking", "speaking", "error",
}
EVENTS = {
    "browser_audio", "interrupt", "state", "listen_start", "listen_stop",
    "uplink_first_frame", "downlink_first_frame",
    "stt", "tts_start", "tts_stop", "tts_sentence", "tool_start", "tool_end",
    "timeout", "reset", "connection_error", "connection_closed", "command_error",
    "action_start", "action_end",
    "voice_route", "local_asr", "local_end",
}
ENUMS = {
    "output_state": {"uninitialized", "running", "suspended", "interrupted", "closed"},
    "state": STATES,
    "mode": {"cloud", "local_first"},
    "source": {"local", "linx"},
    "route": {"local", "cloud_fallback", "no_speech"},
    "reason": {
        "recording_limit", "response_idle", "playback_idle", "turn_limit", "manual", "browser_idle",
        "matched", "unmatched", "unsupported_context", "empty_or_long", "plan_limit",
        "asr_timeout", "asr_unavailable", "no_speech",
    },
    "tool": {
        "duck_nod", "duck_walk_short", "duck_stop", "duck_get_status",
        "duck_flash_step", "duck_bear_shake", "duck_turn_left", "duck_turn_right",
        "duck_set_scene", "duck_kick", "duck_find_companion", "duck_duo_walk",
        "duck_collide", "duck_chorus", "duck_pick_up", "duck_carry", "duck_put_down",
        "duck_sit", "duck_stand",
        "duck_backward", "duck_strafe_left", "duck_strafe_right",
        "duck_shake_head", "duck_tilt_head", "duck_roulade", "duck_ground_pick",
        "duck_skate", "duck_roller_crouch", "duck_yawn", "duck_idle_on", "duck_idle_off",
        "duck_direct", "duck_deliver", "duck_conduct", "duck_recipe", "duck_coach",
        "duck_game", "duck_discuss", "duck_focus", "duck_task",
    },
    "method": {"initialize", "tools/list", "tools/call", "notifications/initialized"},
    "result": {"ok", "error", "ignored", "completed", "failed", "cancelled", "aborted"},
    "backend": {"preview", "robotd", "mujoco"},
    "error_type": {
        "TimeoutError", "OSError", "ValueError", "RuntimeError", "TypeError",
        "JSONDecodeError", "InvalidStatus", "InvalidURI", "ConnectionClosedError",
        "ConnectionClosedOK", "HTTPStatusError", "ConnectTimeout", "ReadTimeout",
        "ConnectError", "WebSocketDisconnect",
    },
}
PLAYBACK_COUNTERS = {
    "received_frames", "scheduled_frames", "ended_frames", "dropped_frames",
    "queued_ms", "signal_peak_milli", "output_sample_rate",
}
COUNTERS = {
    "turn", "call", "uplink_frames", "downlink_frames", "elapsed_ms", "text_chars", "asr_ms",
}
COUNTERS |= PLAYBACK_COUNTERS


def redact_transcript(text, sensitive_values=()):
    if not isinstance(text, str):
        return ""
    for value in sorted(set(sensitive_values), key=len, reverse=True):
        if value:
            text = text.replace(value, "[已隐藏]")
    text = re.sub(r"https?://\S+|wss?://\S+", "[已隐藏链接]", text)
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "[已隐藏设备标识]", text)
    text = re.sub(
        r"(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", "[已隐藏标识]", text
    )
    text = re.sub(
        r"(?i)(?:bearer\s+|(?:api[_ -]?key|token|device[_ -]?id|client[_ -]?id|密钥)"
        r"\s*[:=：]\s*)[^\s，。；]+", "[已隐藏凭据]", text,
    )
    return text[:2000]


class VoiceDiagnostics:
    def __init__(self, path: Path | None = None, *, capacity=200, max_bytes=262144,
                 experience=None):
        self.path = path
        self.events = deque(maxlen=capacity)
        self.sequence = 0
        self.max_bytes = max_bytes
        self.storage_ok = True
        self.turn_sequence = 0
        self.statistics = VoiceStatistics()
        self.playback = None
        self.playback_logged_at = 0.0
        self.experience = experience

    def update_playback(self, data):
        state = data.get("output_state")
        if not isinstance(state, str) or state not in ENUMS["output_state"]:
            raise ValueError("无效的浏览器声音状态")
        snapshot = {"output_state": data["output_state"]}
        for key in PLAYBACK_COUNTERS:
            value = data.get(key)
            if type(value) is int and 0 <= value <= 2**31 - 1:
                snapshot[key] = value
        changed = not self.playback or self.playback["output_state"] != snapshot["output_state"]
        self.playback = snapshot
        now = time.monotonic()
        if changed or now - self.playback_logged_at >= 1:
            self.record("browser_audio", **snapshot)
            self.playback_logged_at = now

    def next_turn(self):
        self.turn_sequence += 1
        return self.turn_sequence

    def record(self, event: str, *, sensitive_values=(), **fields):
        self.sequence += 1
        entry = {
            "id": self.sequence,
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "event": event if event in EVENTS else "unknown",
        }
        for key, value in fields.items():
            if key in ENUMS and isinstance(value, str) and value in ENUMS[key]:
                entry[key] = value
            elif key in COUNTERS and type(value) is int and 0 <= value <= 2**31 - 1:
                entry[key] = value
            elif key == "text" and event == "stt":
                entry[key] = redact_transcript(value, sensitive_values)
        self.events.append(entry)
        self.statistics.observe(entry, time.monotonic())
        if self.experience and event in {
            "listen_start", "listen_stop", "stt", "local_asr", "voice_route", "local_end",
            "action_start", "downlink_first_frame", "tts_stop", "timeout", "reset",
            "interrupt", "connection_error", "command_error", "state",
        }:
            row = next((r for r in reversed(self.statistics.rounds)
                        if r["turn"] == entry.get("turn")), None)
            if row:
                self.experience.observe(entry, row)
        if self.path is not None:
            self._write(entry)

    def _write(self, entry):
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            size = self.path.stat().st_size if self.path.exists() else 0
            if size + len(line.encode()) > self.max_bytes:
                self.path.replace(self.path.with_suffix(".jsonl.1"))
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(line)
            self.storage_ok = True
        except OSError:
            # Disk failures must not take down voice or leak exception paths/data.
            self.storage_ok = False

    def snapshot(self):
        return {"events": list(self.events), "storage_ok": self.storage_ok,
                "browser_audio": self.playback}

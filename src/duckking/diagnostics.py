"""Bounded metadata journal without transcripts, audio, cloud/device IDs, or credentials."""

import json
import os
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

STATES = {
    "disconnected", "connecting", "recovering", "awaiting_binding", "ready",
    "listening", "thinking", "speaking", "error",
}
EVENTS = {
    "state", "listen_start", "listen_stop", "uplink_first_frame", "downlink_first_frame",
    "stt", "tts_start", "tts_stop", "tts_sentence", "tool_start", "tool_end",
    "timeout", "reset", "connection_error", "connection_closed", "command_error",
}
ENUMS = {
    "state": STATES,
    "reason": {"recording_limit", "response_idle", "playback_idle", "turn_limit", "manual"},
    "tool": {
        "duck_nod", "duck_walk_short", "duck_stop", "duck_get_status",
        "duck_flash_step", "duck_bear_shake",
    },
    "method": {"initialize", "tools/list", "tools/call", "notifications/initialized"},
    "result": {"ok", "error", "ignored"},
    "error_type": {
        "TimeoutError", "OSError", "ValueError", "RuntimeError", "TypeError",
        "JSONDecodeError", "InvalidStatus", "InvalidURI", "ConnectionClosedError",
        "ConnectionClosedOK", "HTTPStatusError", "ConnectTimeout", "ReadTimeout",
        "ConnectError", "WebSocketDisconnect",
    },
}
COUNTERS = {"turn", "uplink_frames", "downlink_frames", "elapsed_ms", "text_chars"}


class VoiceDiagnostics:
    def __init__(self, path: Path | None = None, *, capacity=200, max_bytes=262144):
        self.path = path
        self.events = deque(maxlen=capacity)
        self.sequence = 0
        self.max_bytes = max_bytes
        self.storage_ok = True

    def record(self, event: str, **fields):
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
        self.events.append(entry)
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
        return {"events": list(self.events), "storage_ok": self.storage_ok}

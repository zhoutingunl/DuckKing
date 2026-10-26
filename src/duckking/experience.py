"""Persistent, bounded measurements. No speech, audio, user identity, or raw URL."""

import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .statistics import distribution

Page = Literal["home", "scenarios", "demos", "studio", "unknown"]
Traffic = Literal["interactive", "demo", "verification", "unattributed"]
Device = Literal["mobile", "desktop", "unknown"]
Scene = Literal["ball", "duo", "carry", "skills", "rollers", "table", "seated", "stage", "unknown"]
METRICS = {
    "model_ms", "scene_ms", "navigation_ms", "manifest_ms", "asset_ms", "parse_ms",
    "assemble_ms", "first_frame_ms", "stt_local_ms", "stt_cloud_ms", "action_ms",
    "audio_ms", "reply_ms", "asr_ms",
}


class ExperienceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    page: Page = "unknown"
    traffic: Traffic = "unattributed"
    device: Device = "unknown"
    transport: Literal["websocket", "https-poll", "unknown"] = "unknown"
    scene: Scene = "unknown"


class ExperienceEvent(ExperienceContext):
    sequence: int = Field(ge=1, le=1000)
    kind: Literal["load", "voice"]
    status: Literal["started", "waiting", "completed", "failed", "cancelled", "timeout",
                    "abandoned"]
    route: Literal["pending", "local", "cloud", "cloud_fallback", "no_speech"] = "pending"
    cache: Literal["network", "http", "persistent", "memory", "unknown"] = "unknown"
    backend: Literal["preview", "robotd", "mujoco", "unknown"] = "unknown"
    metrics: dict[str, Annotated[float, Field(ge=0, le=86400000, allow_inf_nan=False)]] = Field(
        default_factory=dict, max_length=len(METRICS)
    )
    hidden: bool = False

    @field_validator("metrics")
    @classmethod
    def known_metrics(cls, value):
        if set(value)-METRICS:
            raise ValueError("unknown metric")
        return value


class ExperienceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[ExperienceEvent] = Field(min_length=1, max_length=20)


class ExperienceStore:
    """One bounded writer queue keeps disk I/O off the voice/physics event loop."""

    def __init__(self, path: Path, release="development", *, retention_days=90, capacity=50000):
        self.path, self.release = path, release
        self.retention_days, self.capacity = retention_days, capacity
        self.queue = queue.Queue(maxsize=2048)
        self.storage_ok, self.dropped, self.closed = True, 0, False
        self.worker = None
        self.lock = threading.Lock()

    def submit(self, event, *, source, room):
        item = (event.model_dump(mode="json"), source, room, time.time())
        with self.lock:
            if self.closed:
                return False
            if self.worker is None:
                self.worker = threading.Thread(target=self._work, daemon=True)
                self.worker.start()
            try:
                self.queue.put_nowait(item)
                return True
            except queue.Full:
                self.dropped += 1
                return False

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        db = sqlite3.connect(self.path, timeout=3)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""CREATE TABLE IF NOT EXISTS samples (
            id TEXT, source TEXT, at REAL, updated REAL, sequence INTEGER, room TEXT,
            release TEXT, page TEXT, traffic TEXT, device TEXT, transport TEXT,
            kind TEXT, status TEXT, route TEXT, cache TEXT, backend TEXT, hidden INTEGER,
            metrics TEXT, scene TEXT, PRIMARY KEY (id, source))""")
        db.execute("CREATE INDEX IF NOT EXISTS samples_at ON samples(at)")
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('since', ?)", (str(time.time()),))
        db.commit()
        return db

    def _work(self):
        db = None
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                event, source, room, now = item
                db = db or self._connect()
                values = [event["id"], source, now, now, event["sequence"], room, self.release]
                values += [event[k] for k in ("page", "traffic", "device", "transport", "kind",
                                               "status", "route", "cache", "backend", "hidden")]
                values.extend([json.dumps(event["metrics"]), event["scene"]])
                db.execute("""INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id,source) DO UPDATE SET updated=excluded.updated,
                    sequence=excluded.sequence,status=excluded.status,route=excluded.route,
                    cache=excluded.cache,hidden=excluded.hidden,metrics=excluded.metrics,
                    scene=excluded.scene,backend=excluded.backend
                    WHERE excluded.sequence > samples.sequence""", values)
                db.execute("DELETE FROM samples WHERE at < ?", (now-self.retention_days*86400,))
                db.execute("""DELETE FROM samples WHERE rowid IN
                    (SELECT rowid FROM samples ORDER BY at DESC LIMIT -1 OFFSET ?)""",
                           (self.capacity,))
                db.commit()
                self.storage_ok = True
            except (OSError, sqlite3.Error):
                self.storage_ok = False
                self.dropped += 1
                if db:
                    db.close()
                db = None
            finally:
                self.queue.task_done()
                if item is None and db:
                    db.close()

    def flush(self):
        self.queue.join()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self.worker:
                self.queue.put(None)
        if self.worker:
            self.worker.join(timeout=10)

    def snapshot(self, *, hours=168, traffic="interactive", page="all", device="all",
                 cache="all", room="all", release="all", backend="all", scene="all", now=None):
        now = time.time() if now is None else now
        filters = dict(traffic=traffic, page=page, device=device, cache=cache, room=room,
                       release=release, backend=backend, scene=scene)
        rows, since, releases = [], None, []
        if self.path.exists():
            try:
                with closing(sqlite3.connect(
                    f"file:{self.path}?mode=ro", uri=True, timeout=3
                )) as db:
                    db.row_factory = sqlite3.Row
                    clauses, params = ["at >= ?", "at <= ?"], [now-min(hours, 2160)*3600, now]
                    for key, value in filters.items():
                        if value != "all":
                            clauses.append(f"{key} = ?")
                            params.append(value)
                    rows = [dict(r) for r in db.execute(
                        "SELECT * FROM samples WHERE " + " AND ".join(clauses), params)]
                    since = float(db.execute("SELECT value FROM metadata WHERE key='since'")
                                  .fetchone()[0])
                    releases = [r[0] for r in db.execute(
                        "SELECT DISTINCT release FROM samples ORDER BY at DESC LIMIT 30")]
            except sqlite3.Error:
                self.storage_ok = False
        groups, trend, outcomes = defaultdict(list), defaultdict(list), Counter()
        statuses = Counter()
        for row in rows:
            status = row["status"]
            if status in {"started", "waiting"} and now-row["updated"] > 180:
                status = "abandoned"  # No claim of success after tab loss / service restart.
            statuses[status] += 1
            outcomes[(row["source"], row["kind"], row["route"], status)] += 1
            values = json.loads(row["metrics"])
            for metric, value in values.items():
                # Partial failed loads are not successful load latency samples.
                if row["kind"] == "load" and status != "completed":
                    continue
                key = (row["source"], metric, row["route"])
                groups[key].append(value)
                bucket = datetime.fromtimestamp(row["at"], UTC).strftime(
                    "%Y-%m-%dT%H:00:00Z" if hours <= 24 else "%Y-%m-%dT00:00:00Z")
                trend[(bucket, *key)].append(value)
        return {
            "storage_ok": self.storage_ok, "dropped_since_start": self.dropped,
            "queued": self.queue.qsize(), "retention_days": self.retention_days,
            "capacity": self.capacity, "collection_started_at": since,
            "from": now-hours*3600, "to": now, "filters": filters, "releases": releases,
            "samples": len(rows), "statuses": dict(statuses),
            "hidden_samples": sum(r["hidden"] for r in rows),
            "groups": [dict(source=s, metric=m, route=r, **distribution(v))
                       for (s, m, r), v in sorted(groups.items())],
            "trend": [dict(at=b, source=s, metric=m, route=r, **distribution(v))
                      for (b, s, m, r), v in sorted(trend.items())],
            "outcomes": [dict(source=s, kind=k, route=r, status=t, count=n)
                         for (s, k, r, t), n in sorted(outcomes.items())],
        }


class VoiceExperience:
    def __init__(self, store, room):
        self.store, self.room = store, room
        self.pending = None
        self.contexts = {}

    def observe(self, entry, row):
        turn = row["turn"]
        if entry["event"] == "listen_start":
            self.contexts[turn] = self.pending or ExperienceContext(id=uuid.uuid4())
            self.pending = None
            if len(self.contexts) > 500:
                del self.contexts[next(iter(self.contexts))]
        context = self.contexts.get(turn)
        if not context:
            return
        timing, metrics = row["timings"], {}
        for name, key in [("local_stt", "stt_local_ms"), ("cloud_stt", "stt_cloud_ms"),
                          ("action_start", "action_ms"), ("first_audio", "audio_ms"),
                          ("reply_end", "reply_ms")]:
            if name in timing and "listen_stop" in timing and timing[name] >= timing["listen_stop"]:
                metrics[key] = timing[name]-timing["listen_stop"]
        if isinstance(row.get("asr_ms"), int):
            metrics["asr_ms"] = row["asr_ms"]
        status = {"listening": "started", "error": "failed", "interrupted": "cancelled"}.get(
            row["status"], row["status"])
        # Journal sequence is not bounded to a turn; use an independent per-row sequence.
        row["experience_sequence"] = row.get("experience_sequence", 0) + 1
        event = ExperienceEvent(**context.model_dump(), sequence=row["experience_sequence"],
                                kind="voice", status=status, route=row["route"],
                                backend=row["backend"], metrics=metrics)
        self.store.submit(event, source="server", room=self.room)

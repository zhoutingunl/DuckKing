"""Anonymous scene engagement and once-per-Beijing-day ranking snapshots.

Click × mean active time equals total active time. Only acknowledged, monotonic
heartbeats accrue time; background tabs and loading screens are excluded by the
client, and the server additionally caps credit to elapsed wall time.
"""

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

RECOMMENDED = (
    "basketball",
    "stilts",
    "acrobatics",
    "red_light",
    "tug",
    "giant_ball",
    "director",
    "long_jump",
    "dock",
    "roller_slalom",
)


class VisitEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    capability: str = Field(min_length=1, max_length=80)
    operation: Literal["start", "pulse", "end"]
    sequence: int = Field(ge=0, le=100000)
    active_ms: int = Field(ge=0, le=86400000)


class SceneDiscovery:
    def __init__(self, path: Path, *, clock=time.time):
        self.path, self.clock, self.lock = path, clock, threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS scenes (
                    id TEXT PRIMARY KEY, added REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS totals (
                    scene TEXT PRIMARY KEY, clicks INTEGER DEFAULT 0,
                    active_ms INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS visits (
                    id TEXT PRIMARY KEY, scope TEXT, scene TEXT, started REAL,
                    updated REAL, sequence INTEGER, reported INTEGER,
                    credited INTEGER DEFAULT 0, ended INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS rankings (
                    day TEXT PRIMARY KEY, snapshot TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def catalog(self, entries, sort="top", metric="engagement"):
        now = self.clock()
        day = datetime.fromtimestamp(now, ZoneInfo("Asia/Shanghai")).date().isoformat()
        with self.lock, closing(self.connect()) as db, db:
            for key in reversed(entries):
                db.execute("INSERT OR IGNORE INTO scenes VALUES (?, ?)", (key, now))
            saved = db.execute("SELECT snapshot FROM rankings WHERE day=?", (day,)).fetchone()
            if saved is None:
                totals = {r["scene"]: dict(r) for r in db.execute("SELECT * FROM totals")}
                db.execute("INSERT INTO rankings VALUES (?,?)", (day, json.dumps(totals)))
                db.execute("DELETE FROM rankings WHERE day < ?", (day[:7] + "-01",))
            else:
                totals = json.loads(saved[0])
            records = list(db.execute("SELECT rowid AS ordinal,* FROM scenes"))
            added = {r["id"]: r["added"] for r in records}
            ordinal = {r["id"]: r["ordinal"] for r in records}
        fallback = {key: index for index, key in enumerate(RECOMMENDED)}

        def order(key):
            values = totals.get(key, {})
            score = values.get("active_ms" if metric == "engagement" else "clicks", 0)
            return (-score, -values.get("clicks", 0), fallback.get(key, 1000), key)

        keys = sorted(
            entries, key=(lambda key: (-added[key], -ordinal[key])) if sort == "latest" else order
        )
        return {
            "capabilities": [
                dict(
                    id=key,
                    **entries[key],
                    added_at=added[key],
                    usage=totals.get(key, {"clicks": 0, "active_ms": 0}),
                )
                for key in keys
            ],
            "ranking": {
                "day": day,
                "timezone": "Asia/Shanghai",
                "sort": sort,
                "metric": metric,
                "recommended": not any(r.get("clicks", 0) for r in totals.values()),
                "recommended_ids": [k for k in RECOMMENDED if k in entries],
            },
        }

    def event(self, event, scope, entries):
        if event.capability not in entries:
            raise ValueError("未知功能场景")
        now = self.clock()
        scope = hashlib.sha256(scope.encode()).hexdigest()
        with self.lock, closing(self.connect()) as db, db:
            db.execute("DELETE FROM visits WHERE updated < ?", (now - 86400,))
            old = db.execute("SELECT * FROM visits WHERE id=?", (event.id,)).fetchone()
            if old is None:
                if event.operation != "start":
                    return
                if db.execute("SELECT count(*) FROM visits WHERE ended=0").fetchone()[0] >= 512:
                    return
                if (
                    db.execute(
                        "SELECT count(*) FROM visits WHERE scope=? AND started>?", (scope, now - 60)
                    ).fetchone()[0]
                    >= 30
                ):
                    return
                db.execute(
                    "INSERT INTO visits VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        event.id,
                        scope,
                        event.capability,
                        now,
                        now,
                        event.sequence,
                        0,
                        0,
                        0,
                    ),
                )
                db.execute(
                    "INSERT INTO totals(scene,clicks) VALUES (?,1) "
                    "ON CONFLICT(scene) DO UPDATE SET clicks=clicks+1",
                    (event.capability,),
                )
                return
            if old["scope"] != scope or old["scene"] != event.capability:
                raise ValueError("体验记录不属于当前房间")
            if old["ended"] or event.sequence <= old["sequence"] or event.operation == "start":
                return
            # A late/offline pulse cannot turn a forgotten tab into hours of use.
            delta = max(
                0,
                min(
                    event.active_ms - old["reported"],
                    int(max(0, now - old["updated"]) * 1000),
                    15000,
                ),
            )
            db.execute(
                "UPDATE visits SET updated=?,sequence=?,reported=?,credited=credited+?,"
                "ended=? WHERE id=?",
                (
                    now,
                    event.sequence,
                    max(old["reported"], event.active_ms),
                    delta,
                    event.operation == "end",
                    event.id,
                ),
            )
            db.execute(
                "UPDATE totals SET active_ms=active_ms+? WHERE scene=?", (delta, event.capability)
            )

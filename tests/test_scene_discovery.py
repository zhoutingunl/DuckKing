import uuid
from datetime import UTC

import pytest

from duckking.scene_discovery import MAX_VISIT_ACTIVE_MS, SceneDiscovery, VisitEvent


def event(id, capability="basketball", operation="start", sequence=1, active_ms=0):
    return VisitEvent(
        id=id, capability=capability, operation=operation, sequence=sequence, active_ms=active_ms
    )


def test_daily_snapshot_persists_and_new_scenes_keep_real_added_time(tmp_path):
    now = [1800000000.0]
    store = SceneDiscovery(tmp_path / "usage.sqlite3", clock=lambda: now[0])
    entries = {"movement": {}, "basketball": {}, "hop": {}}
    initial = store.catalog(entries)
    assert initial["ranking"]["recommended"]
    assert initial["capabilities"][0]["id"] == "basketball"
    id = str(uuid.uuid4())
    store.event(event(id, "hop"), "room-lease", entries)
    now[0] += 10
    store.event(event(id, "hop", "pulse", 2, 10000), "room-lease", entries)
    assert store.catalog(entries) == initial  # stable throughout the day
    now[0] += 86400
    snapshot = store.catalog(entries)
    assert snapshot["capabilities"][0]["id"] == "hop"
    assert snapshot["capabilities"][0]["usage"]["active_ms"] == 10000
    assert not snapshot["ranking"]["recommended"]
    assert SceneDiscovery(store.path, clock=lambda: now[0]).catalog(entries) == snapshot
    now[0] += 1
    entries["new_skill"] = {}
    latest = store.catalog(entries, "latest")["capabilities"]
    assert latest[0]["id"] == "new_skill"
    assert latest[0]["added_at"] > latest[-1]["added_at"]


def test_dedupe_foreign_scope_and_bounded_wall_time(tmp_path):
    now = [1000.0]
    store = SceneDiscovery(tmp_path / "usage.sqlite3", clock=lambda: now[0])
    entries = {"basketball": {}}
    id = str(uuid.uuid4())
    store.event(event(id), "a", entries)
    store.event(event(id), "a", entries)
    now[0] += 5
    with pytest.raises(ValueError, match="当前房间"):
        store.event(event(id, operation="pulse", sequence=2, active_ms=10000), "b", entries)
    store.event(event(id, operation="pulse", sequence=2, active_ms=10000), "a", entries)
    store.event(event(id, operation="pulse", sequence=2, active_ms=10000), "a", entries)
    now[0] += 300
    store.event(event(id, operation="end", sequence=3, active_ms=600000), "a", entries)
    store.event(event(id, operation="pulse", sequence=4, active_ms=900000), "a", entries)
    row = store.catalog(entries)["capabilities"][0]["usage"]
    assert row["clicks"] == 1
    assert row["active_ms"] == 20000  # 5 s elapsed + at most 15 s late pulse
    with pytest.raises(ValueError, match="未知"):
        store.event(event(str(uuid.uuid4()), "invalid"), "a", entries)


def test_ranking_always_uses_effective_time_not_click_count(tmp_path):
    now = [1000.0]
    store = SceneDiscovery(tmp_path / "usage.sqlite3", clock=lambda: now[0])
    entries = {"hop": {}, "basketball": {}}
    for _ in range(3):
        store.event(event(str(uuid.uuid4()), "hop"), "a", entries)
    id = str(uuid.uuid4())
    store.event(event(id), "a", entries)
    now[0] += 10
    store.event(event(id, operation="end", sequence=2, active_ms=10000), "a", entries)
    ranked = store.catalog(entries)
    assert ranked["capabilities"][0]["id"] == "basketball"
    assert ranked["ranking"]["metric"] == "engagement"


def test_one_visit_cannot_accrue_more_than_five_minutes_across_restarts(tmp_path):
    now = [1000.0]
    path = tmp_path / "usage.sqlite3"
    entries = {"basketball": {}}
    visit = str(uuid.uuid4())
    store = SceneDiscovery(path, clock=lambda: now[0])
    store.event(event(visit), "owner", entries)
    for sequence in range(2, 70):
        now[0] += 15
        store = SceneDiscovery(path, clock=lambda: now[0])
        store.event(event(visit, operation="pulse", sequence=sequence,
                          active_ms=(sequence - 1) * 15000), "owner", entries)
    row = store.catalog(entries)["capabilities"][0]["usage"]
    assert row == {"scene": "basketball", "clicks": 1, "active_ms": MAX_VISIT_ACTIVE_MS}
    assert store.catalog(entries)["ranking"]["visit_cap_ms"] == MAX_VISIT_ACTIVE_MS


def test_beijing_midnight_is_the_snapshot_boundary(tmp_path):
    from datetime import datetime

    now = [datetime(2026, 11, 13, 15, 59, 59, tzinfo=UTC).timestamp()]
    store = SceneDiscovery(tmp_path / "usage.db", clock=lambda: now[0])
    assert store.catalog({"a": {}})["ranking"]["day"] == "2026-11-13"
    now[0] += 1
    assert store.catalog({"a": {}})["ranking"]["day"] == "2026-11-14"

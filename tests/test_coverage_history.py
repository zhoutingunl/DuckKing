import json
import shutil

import pytest

from duckking.deployment import DeploymentStatus
from duckking.release_coverage import load_coverage, persist_coverage


def report(commit, covered=90):
    return {
        "commit": commit,
        "scope": "backend",
        "source_url": "https://github.com/zhoutingunl/DuckKing/actions/runs/123",
        "lines": {"covered": covered, "total": 100},
        "branches": {"covered": 80, "total": 100},
    }


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def test_upgrade_recovers_old_reports_and_survives_release_pruning(tmp_path):
    old, new = "a" * 40, "b" * 40
    old_release, new_release = tmp_path / "releases/old", tmp_path / "releases/new"
    first = write(old_release / "release-coverage.json", [report(old)])
    second = write(new_release / "release-coverage.json", [report(new, 96)])
    history = tmp_path / "data/deployments.jsonl"
    history.parent.mkdir()
    history.write_text("\n".join(json.dumps({
        "version": version, "commit": commit, "status": "success", "target": "yzh737"
    }) for version, commit in [("old", old), ("new", new), ("unknown", "c" * 40)]))
    status = DeploymentStatus(new_release / "release.json", history)
    assert status.snapshot()["records"][2]["coverage"] is None
    store = history.with_name("release-coverage.json")
    assert persist_coverage(store, [first, second]) == 2
    # An already running process sees restored history on its next page refresh.
    rows = status.snapshot()["records"]
    assert [row["coverage"] for row in rows] == [None, report(new, 96), report(old)]
    shutil.rmtree(old_release)
    assert persist_coverage(store, [second]) == 2
    assert DeploymentStatus(new_release / "release.json", history).snapshot() == status.snapshot()
    assert store.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("bad", [None, {}, [None], [report("x" * 40)], [0] * 2001])
def test_invalid_migration_keeps_existing_evidence(tmp_path, bad):
    original = [report("a" * 40)]
    store = write(tmp_path / "store.json", original)
    source = write(tmp_path / "source.json", bad)
    with pytest.raises(ValueError):
        persist_coverage(store, [source])
    assert json.loads(store.read_text()) == original
    assert not list(tmp_path.glob(".coverage-*"))


def test_corrupt_existing_store_is_not_silently_replaced(tmp_path):
    store = tmp_path / "store.json"
    store.write_text("broken")
    source = write(tmp_path / "source.json", [report("a" * 40)])
    with pytest.raises(ValueError):
        persist_coverage(store, [source])
    assert store.read_text() == "broken"


def test_failed_atomic_replace_preserves_previous_store(tmp_path, monkeypatch):
    original = [report("a" * 40)]
    store = write(tmp_path / "store.json", original)
    source = write(tmp_path / "source.json", [report("b" * 40)])

    def fail(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("duckking.release_coverage.os.replace", fail)
    with pytest.raises(OSError):
        persist_coverage(store, [source])
    assert json.loads(store.read_text()) == original
    assert not list(tmp_path.glob(".coverage-*"))


def test_migration_strips_private_fields_and_current_report_has_precedence(tmp_path):
    commit = "a" * 40
    source = write(tmp_path / "input.json", [report(commit) | {"token": "private"}])
    store = tmp_path / "data/release-coverage.json"
    store.parent.mkdir()
    persist_coverage(store, [source, source])
    assert load_coverage(store) == {commit: report(commit)}
    assert "private" not in store.read_text()
    history = store.with_name("deployments.jsonl")
    history.write_text(json.dumps({"version": "new", "commit": commit, "status": "success"}))
    release = tmp_path / "current/release.json"
    write(release.with_name("release-coverage.json"), [report(commit, 97)])
    status = DeploymentStatus(release, history)
    assert status.snapshot()["records"][0]["coverage"] == report(commit, 97)
    store.write_text("broken")
    assert status.snapshot()["records"][0]["coverage"] == report(commit, 97)

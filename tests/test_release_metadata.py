import json
import runpy

import pytest

from duckking.deployment import DeploymentStatus
from duckking.release_changes import CommitHistory
from duckking.release_coverage import load_coverage, public_coverage


def sha(letter):
    return letter * 40


def catalog(tmp_path):
    rows = [
        {"commit": sha(name), "parents": [sha(p) for p in parents], "subject": f"change {name}"}
        for name, parents in [
            ("f", "e"),
            ("e", "cd"),
            ("d", "b"),
            ("c", "b"),
            ("b", "a"),
            ("a", ""),
        ]
    ]
    path = tmp_path / "release-commits.json"
    path.write_text(json.dumps(rows))
    return path


def evidence(commit=None):
    return {
        "commit": commit or sha("e"),
        "scope": "backend",
        "source_url": "https://github.com/zhoutingunl/DuckKing/actions/runs/123",
        "lines": {"covered": 97, "total": 100},
        "branches": {"covered": 93, "total": 100},
    }


def test_commit_dag_uses_reachability_and_retains_rollback_history(tmp_path):
    history = CommitHistory(catalog(tmp_path))
    changes = history.changes(sha("e"), sha("b"))
    assert [r["commit"] for r in changes["changes"]] == [sha("e"), sha("d"), sha("c")]
    assert changes["change_count"] == 3 and changes["change_state"] == "available"
    assert history.changes(sha("a"), None)["change_state"] == "initial"
    assert history.changes(sha("b"), sha("e"))["change_state"] == "rollback"
    assert history.changes(sha("b"), sha("b"))["change_state"] == "identical"
    assert history.changes(sha("e"), sha("a"))["change_count"] == 4
    assert history.changes("invalid", None)["change_state"] == "unavailable"
    assert history.changes(sha("e"), sha("9"))["change_state"] == "unavailable"
    assert history.changes(sha("9"), None)["change_state"] == "unavailable"
    assert history.changes(sha("9"), None)["change_count"] is None
    assert "parents" not in json.dumps(changes)


@pytest.mark.parametrize("value", [None, {}, [None], [{"commit": "invalid"}], [0] * 2001])
def test_invalid_catalog_never_invents_changes(tmp_path, value):
    path = tmp_path / "release-commits.json"
    path.write_text(json.dumps(value))
    assert CommitHistory(path).changes(sha("e"), sha("b"))["change_state"] == "unavailable"


def test_duplicate_and_missing_ancestry_are_unavailable_and_lists_are_bounded(tmp_path):
    path = catalog(tmp_path)
    rows = json.loads(path.read_text())
    path.write_text(json.dumps(rows + rows[:1]))
    assert not CommitHistory(path).commits
    path.write_text(json.dumps(rows[:-1]))
    assert CommitHistory(path).changes(sha("e"), None)["change_state"] == "unavailable"
    rows = [
        {"commit": f"{i:040x}", "parents": [f"{i - 1:040x}"] if i else [], "subject": "x" * 500}
        for i in range(60)
    ]
    path.write_text(json.dumps(list(reversed(rows))))
    result = CommitHistory(path).changes(f"{59:040x}", None)
    assert result["change_count"] == 60 and len(result["changes"]) == 50
    assert len(result["changes"][0]["subject"]) == 300
    path.write_text("invalid JSON")
    assert not CommitHistory(path).commits
    assert not CommitHistory(tmp_path).commits


def test_deploy_baselines_ignore_failures_reuse_staged_baseline_and_isolate_targets(tmp_path):
    catalog(tmp_path)
    history = tmp_path / "history.jsonl"
    values = [
        ("one", "b", "success", "x"),
        ("failed", "d", "failed", "x"),
        ("two", "c", "success", "x"),
        ("three", "e", "staged", "x"),
        ("three", "e", "success", "x"),
        ("other-host", "f", "success", "y"),
        ("rollback", "b", "success", "x"),
        ("retry", "b", "success", "x"),
    ]
    history.write_text(
        "\n".join(
            json.dumps(
                {"version": v, "commit": sha(c), "status": s, "target": t, "secret": "never-public"}
            )
            for v, c, s, t in values
        )
    )
    (tmp_path / "release-coverage.json").write_text(
        json.dumps([evidence() | {"token": "never-public"}])
    )
    result = DeploymentStatus(tmp_path / "release.json", history).snapshot()
    rows = list(reversed(result["records"]))
    assert rows[1]["previous_commit"] == rows[2]["previous_commit"] == sha("b")
    assert rows[3]["previous_commit"] == rows[4]["previous_commit"] == sha("c")
    assert rows[3]["changes"] == rows[4]["changes"]
    assert rows[5]["change_state"] == "initial"
    assert rows[6]["change_state"] == "rollback" and rows[7]["change_state"] == "identical"
    assert rows[4]["coverage"] == evidence() and rows[2]["coverage"] is None
    assert "never-public" not in json.dumps(result)
    assert "parents" not in json.dumps(result)
    with history.open("a") as stream:
        for i in range(105):
            stream.write(
                "\n"
                + json.dumps(
                    {
                        "version": f"pending-{i}",
                        "commit": sha("f"),
                        "status": "failed",
                        "target": "x",
                    }
                )
            )
    recent = DeploymentStatus(tmp_path / "release.json", history).snapshot()["records"]
    assert len(recent) == 100 and all(row["previous_commit"] == sha("b") for row in recent)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"scope": "frontend"},
        {"commit": "not-a-sha"},
        {"source_url": "javascript:alert(1)"},
        {"lines": None},
        {"lines": {"covered": True, "total": 1}},
        {"lines": {"covered": 2, "total": 1}},
        {"branches": {"covered": 0, "total": 0}},
    ],
)
def test_coverage_rejects_wrong_scope_unbound_or_invalid_counts(bad):
    assert public_coverage(evidence() | bad if bad else bad) is None


def test_coverage_export_keeps_counts_bound_to_a_commit_and_ignores_unknown_fields(tmp_path):
    report, summary = tmp_path / "coverage.json", tmp_path / "summary.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "covered_lines": 97,
                    "num_statements": 100,
                    "covered_branches": 93,
                    "num_branches": 100,
                }
            }
        )
    )
    export = runpy.run_path("scripts/export_coverage.py")["export"]
    export(report, summary, sha("e"), evidence()["source_url"])
    assert json.loads(summary.read_text()) == evidence()
    with pytest.raises(ValueError):
        export(report, summary, "unknown", evidence()["source_url"])
    summary.write_text(json.dumps([evidence() | {"private": "secret"}, {}]))
    assert load_coverage(summary) == {sha("e"): evidence()}
    summary.write_text("{}")
    assert load_coverage(summary) == {}
    summary.write_text("broken")
    assert load_coverage(summary) == {} and load_coverage(tmp_path) == {}

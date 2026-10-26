"""Only commit-bound, explicitly scoped coverage evidence is exposed publicly."""

import json
import os
import re
import tempfile
from pathlib import Path

from .release_changes import valid_commit


def public_coverage(value):
    if (
        not isinstance(value, dict)
        or not valid_commit(value.get("commit"))
        or value.get("scope") != "backend"
        or not isinstance(value.get("source_url"), str)
        or not re.fullmatch(
            r"https://github\.com/zhoutingunl/DuckKing/actions/runs/[0-9]+", value["source_url"]
        )
    ):
        return None
    result = {key: value[key] for key in ("commit", "scope", "source_url")}
    for metric in ("lines", "branches"):
        counts = value.get(metric)
        if (
            not isinstance(counts, dict)
            or type(counts.get("covered")) is not int
            or type(counts.get("total")) is not int
            or not 0 <= counts["covered"] <= counts["total"]
            or counts["total"] <= 0
        ):
            return None
        result[metric] = {key: counts[key] for key in ("covered", "total")}
    return result


def load_coverage(path: Path):
    try:
        rows = json.loads(path.read_text())
        if not isinstance(rows, list) or len(rows) > 2000:
            return {}
        return {row["commit"]: row for value in rows if (row := public_coverage(value))}
    except (OSError, ValueError):
        return {}


def persist_coverage(destination: Path, sources):
    """Merge verified release reports under the installer's deployment lock.

    Fail before replacing the store if any input is corrupt. Release directories
    may later be pruned without removing historical commit-bound evidence.
    """
    reports = {}
    paths = ([destination] if destination.exists() else []) + list(sources)
    for path in paths:
        values = json.loads(path.read_text())
        if not isinstance(values, list) or len(values) > 2000:
            raise ValueError(f"Invalid coverage collection: {path.name}")
        for value in values:
            report = public_coverage(value)
            if report is None:
                raise ValueError(f"Invalid coverage evidence: {path.name}")
            reports[report["commit"]] = report
    if len(reports) > 2000:
        raise ValueError("Coverage history exceeds 2000 commits")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=destination.parent, prefix=".coverage-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(list(reports.values()), stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(reports)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--releases", type=Path, required=True)
    args = parser.parse_args()
    count = persist_coverage(args.store, sorted(args.releases.glob("*/release-coverage.json")))
    print(f"Preserved coverage evidence for {count} commits")

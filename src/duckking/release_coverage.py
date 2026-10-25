"""Only commit-bound, explicitly scoped coverage evidence is exposed publicly."""

import json
import re
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

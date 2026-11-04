"""Bounded commit summaries from the exact Git history bundled with a release."""

import json
import re
from pathlib import Path

MAX_COMMITS = 2000
MAX_CHANGES = 50


def valid_commit(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{40}", value) is not None


class CommitHistory:
    def __init__(self, path: Path):
        self.commits = {}
        self.cache = {}
        try:
            rows = json.loads(path.read_text())
            if not isinstance(rows, list) or len(rows) > MAX_COMMITS:
                raise ValueError("invalid commit history")
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not valid_commit(row.get("commit"))
                    or not isinstance(row.get("subject"), str)
                    or not isinstance(row.get("parents"), list)
                    or len(row["parents"]) > 16
                    or not all(valid_commit(parent) for parent in row["parents"])
                    or row["commit"] in self.commits
                ):
                    raise ValueError("invalid commit entry")
                self.commits[row["commit"]] = {
                    "subject": " ".join(row["subject"].split())[:300],
                    "parents": row["parents"],
                }
        except (OSError, ValueError):
            self.commits = {}

    def ancestors(self, commit):
        if commit not in self.cache:
            pending, found = [commit], set()
            while pending:
                current = pending.pop()
                if current in found:
                    continue
                if current not in self.commits:
                    self.cache[commit] = None
                    break
                found.add(current)
                pending.extend(self.commits[current]["parents"])
            else:
                self.cache[commit] = found
        return self.cache[commit]

    def changes(self, commit, previous):
        result = {"changes": [], "change_count": None, "change_state": "unavailable"}
        if valid_commit(previous):
            result["previous_commit"] = previous
        if not valid_commit(commit):
            return result
        if commit == previous:
            return result | {"change_count": 0, "change_state": "identical"}
        head = self.ancestors(commit)
        base = self.ancestors(previous) if previous else set()
        if head is None or base is None:
            return result
        added = head - base
        entries = [
            {"commit": sha, "subject": row["subject"]}
            for sha, row in self.commits.items()
            if sha in added
        ]
        state = "rollback" if commit in base else "available" if previous else "initial"
        return result | {
            "changes": entries[:MAX_CHANGES],
            "change_count": len(entries),
            "change_state": state,
        }

"""Public release metadata; private runtime state is never part of this API."""

import json
from collections import deque
from pathlib import Path

FIELDS = ("version", "commit", "built_at", "operator", "git_ref", "target")
RECORD_FIELDS = (*FIELDS, "ts", "status", "selftest", "rollback", "previous_version")


def public_fields(value: dict, fields: tuple) -> dict:
    return {key: value[key][:200] for key in fields if isinstance(value.get(key), str)}


class DeploymentStatus:
    def __init__(self, release_file: Path, history_file: Path):
        self.history_file = history_file
        self.release = {}
        self.warning = None
        # Read once: replacing a symlink must not relabel an already running process.
        try:
            value = json.loads(release_file.read_text())
            if not isinstance(value, dict) or not all(
                isinstance(value.get(k), str) and value[k] for k in FIELDS
            ):
                raise ValueError("invalid release")
            self.release = public_fields(value, FIELDS)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.warning = "发布信息无法读取"

    def snapshot(self) -> dict:
        warnings = [self.warning] if self.warning else []
        rows = deque(maxlen=100)
        try:
            with self.history_file.open() as stream:
                for line in stream:
                    try:
                        value = json.loads(line)
                        if (
                            not isinstance(value, dict)
                            or value.get("status") not in {"success", "failed", "staged"}
                            or not isinstance(value.get("version"), str)
                            or not value["version"]
                        ):
                            raise ValueError("invalid history")
                        rows.append(public_fields(value, RECORD_FIELDS))
                    except ValueError:
                        if "部分部署记录损坏" not in warnings:
                            warnings.append("部分部署记录损坏")
        except FileNotFoundError:
            pass
        except OSError:
            warnings.append("部署记录无法读取")
        records = list(reversed(rows))
        latest = next((r for r in records if r["status"] == "success"), None)
        if self.warning:
            state = "unknown"
        elif not self.release:
            state = "untracked" if records else "development"
        elif (
            records
            and records[0].get("status") == "staged"
            and all(records[0].get(k) == self.release.get(k) for k in ("version", "commit"))
        ):
            state = "staged"
        elif latest is None:
            state = "unrecorded"
        elif any(latest.get(k) != self.release.get(k) for k in ("version", "commit")):
            state = "mismatch"
        else:
            state = "ok"
        return {
            "current": self.release or None,
            "state": state,
            "records": records,
            "warnings": warnings,
        }

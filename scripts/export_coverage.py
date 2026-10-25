"""Bind pytest-cov counts to the PR head tested by this GitHub Actions run."""

import argparse
import json
from pathlib import Path

from duckking.release_coverage import public_coverage


def export(report: Path, output: Path, commit: str, run_url: str):
    totals = json.loads(report.read_text())["totals"]
    result = public_coverage(
        {
            "commit": commit,
            "scope": "backend",
            "source_url": run_url,
            "lines": {"covered": totals["covered_lines"], "total": totals["num_statements"]},
            "branches": {"covered": totals["covered_branches"], "total": totals["num_branches"]},
        }
    )
    if result is None:
        raise ValueError("Invalid coverage evidence")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("coverage.json"))
    parser.add_argument("--output", type=Path, default=Path("coverage-summary.json"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    export(args.report, args.output, args.commit, args.run_url)

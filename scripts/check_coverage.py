"""Separate line and branch thresholds; never hide application modules from coverage."""

import json
import sys

totals = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "coverage.json"))["totals"]
lines = 100 * totals["covered_lines"] / max(totals["num_statements"], 1)
branches = 100 * totals["covered_branches"] / max(totals["num_branches"], 1)
print(f"Backend coverage: lines {lines:.2f}% (>=90%), branches {branches:.2f}% (>=85%)")
if lines < 90 or branches < 85:
    raise SystemExit("Coverage gate failed")

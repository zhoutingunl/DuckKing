#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
uv sync --frozen --extra simulation --python 3.12
uv run --frozen --no-sync python scripts/fetch_scene_assets.py
(cd frontend && npm ci && npm run build)
echo "Ready. Run scripts/run_local.sh and open http://127.0.0.1:8765/scenarios.html"

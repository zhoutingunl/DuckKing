#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
uv sync --frozen --extra simulation --extra local-asr
uv run --frozen --no-sync python scripts/fetch_asr_assets.py
cat <<'HELP'
Offline ASR is ready. Run in two terminals:
  uv run --frozen --no-sync duckking-asr
  DUCKKING_LOCAL_ASR=1 scripts/run_local.sh
The worker binds only 127.0.0.1:8767. Browser microphone setup stays unchanged.
HELP

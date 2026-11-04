#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
if ! command -v uv >/dev/null || [ ! -x .venv/bin/duckking ] || [ ! -f frontend/dist/index.html ]; then
  echo "Local environment or frontend build is missing. Run scripts/setup_local.sh first." >&2
  exit 1
fi

# Keep the application in the foreground, so Ctrl+C also stops active motion.
# Forward explicit backend/port/socket options without falling back to preview.
exec uv run --frozen --no-sync duckking "$@"

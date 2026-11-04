#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
for dependency in uv node npm; do
  command -v "$dependency" >/dev/null || {
    echo "Missing dependency: $dependency. See README.md for local setup." >&2
    exit 1
  }
done
node --input-type=module -e '
  const [major, minor] = process.versions.node.split(".").map(Number);
  if (major < 22 || (major === 22 && minor < 12)) {
    console.error("DuckKing requires Node.js 22.12 or newer.");
    process.exit(1);
  }
'

uv sync --frozen --extra simulation --python 3.12
uv run --frozen --no-sync python scripts/fetch_scene_assets.py
(cd frontend && npm ci && npm run build)

# Preview does not need native audio or a cloud account. Probe only the codec;
# do not load private device settings or initiate OTA during setup.
uv run --frozen --no-sync python - <<'PY'
from duckking.opus import OpusCodec

try:
    codec = OpusCodec()
except (OSError, RuntimeError):
    print("Preview is ready. Voice additionally needs libopus:")
    print("  macOS: brew install opus; Ubuntu: sudo apt-get install libopus0")
else:
    codec.close()
    print("Native Opus is available. Cloud voice still requires explicit connection.")
PY
echo "Setup complete. Run scripts/run_local.sh, then open http://127.0.0.1:8765"

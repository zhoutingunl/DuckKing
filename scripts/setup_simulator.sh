#!/usr/bin/env bash
set -euo pipefail

# Upstream stays outside the application source and retains its own licenses.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
sim_root="${DUCKKING_SIM_DIR:-$repo_root/external}"
mkdir -p "$sim_root"
for command in git uv cargo pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
checkout() {
  local name="$1" revision="$2"
  if [ ! -d "$sim_root/$name/.git" ]; then
    git clone --filter=blob:none --no-checkout "https://github.com/pollen-robotics/$name.git" "$sim_root/$name"
  fi
  if [ -n "$(git -C "$sim_root/$name" status --porcelain)" ] && [ -f "$sim_root/$name/pyproject.toml" -o -f "$sim_root/$name/Cargo.toml" ]; then
    echo "Refusing to change a modified upstream checkout: $sim_root/$name" >&2
    exit 1
  fi
  git -C "$sim_root/$name" checkout "$revision"
}
checkout microduck 942e58e3aa6dbb28e7037203fff11866122c7567
checkout microduck_rl b02fdea4902c2b93b7d34a83a6f05da4ececb7d3
(cd "$sim_root/microduck_rl" && uv sync --frozen --python 3.12)
echo "Simulator dependencies prepared. Run scripts/run_simulator.sh in a separate terminal."

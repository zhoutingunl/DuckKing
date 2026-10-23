#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
sim_root="${DUCKKING_SIM_DIR:-$repo_root/external}"
export DUCK_SIM_RL="$sim_root/microduck_rl"
if [ ! -x "$sim_root/microduck/scripts/duck-sim" ]; then
  echo "First run scripts/setup_simulator.sh" >&2
  exit 1
fi
cd "$sim_root/microduck"
trap 'scripts/duck-sim down' EXIT
trap 'exit 0' INT TERM
scripts/duck-sim
echo "Keep this terminal open. Ctrl+C stops the simulator."
# The parent stays alive so task runners do not reap the background daemon process group.
while true; do sleep 10; done

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Explicit GUI entrypoint for cases where the shell still has old headless
# environment variables hanging around.
export MAP_SIM_GZCLIENT=1
export MAP_SIM_ENABLE_HEADLESS_RENDERING=0
export MAP_SIM_ENABLE_RVIZ="${MAP_SIM_ENABLE_RVIZ:-1}"

exec "$ROOT_DIR/scripts/run_sim.sh" "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export MAP_SIM_ENABLE_DEPTH_CAMERA="${MAP_SIM_ENABLE_DEPTH_CAMERA:-1}"
export MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}"

exec "$ROOT_DIR/scripts/run_sim.sh" "$@"

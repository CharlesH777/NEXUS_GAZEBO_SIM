#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}" \
MAP_SIM_ENABLE_RVIZ="${MAP_SIM_ENABLE_RVIZ:-1}" \
exec "$ROOT_DIR/run_sim_street_infer.sh" "$@"

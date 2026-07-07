#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}" \
MAP_SIM_ENABLE_RVIZ="${MAP_SIM_ENABLE_RVIZ:-1}" \
MAP_SIM_ENABLE_DEFAULT_STACK="${MAP_SIM_ENABLE_DEFAULT_STACK:-0}" \
MAP_SIM_ENABLE_ELEVATION_MAPPING="${MAP_SIM_ENABLE_ELEVATION_MAPPING:-1}" \
MAP_SIM_ENABLE_MPPI_NAVIGATION="${MAP_SIM_ENABLE_MPPI_NAVIGATION:-1}" \
bash "$ROOT_DIR/project_identity/logo/play_logo_intro.sh" 30 golden || true
exec "$ROOT_DIR/scripts/run_sim.sh" "$@"

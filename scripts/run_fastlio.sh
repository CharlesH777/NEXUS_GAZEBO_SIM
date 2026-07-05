#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$ROOT_DIR/scripts/build_fastlio.sh" ]; then
  chmod +x "$ROOT_DIR/scripts/build_fastlio.sh"
fi

FASTLIO_BIN="${MAP_SIM_FASTLIO2_BIN:-/home/charles/桌面/slam_2026_charles/src/FASTLIO2_ROS2/install_nexus/fastlio2/lib/fastlio2/lio_node}"
if [ ! -x "$FASTLIO_BIN" ]; then
  echo "[INFO] FAST-LIO2 binary not found, building it first..."
  bash "$ROOT_DIR/scripts/build_fastlio.sh"
fi

MAP_SIM_ENABLE_POINTCLOUD_PIPELINE="${MAP_SIM_ENABLE_POINTCLOUD_PIPELINE:-1}" \
MAP_SIM_ENABLE_FASTLIO2="${MAP_SIM_ENABLE_FASTLIO2:-1}" \
bash "$ROOT_DIR/scripts/run_sim.sh" "$@"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POINTCEPT_DIR="${MAP_SIM_POINTCEPT_ROOT:-$ROOT_DIR/Pointcept}"
POINTCEPT_ENV="${MAP_SIM_POINTCEPT_ENV:-$POINTCEPT_DIR/.conda-env}"
POINTCEPT_CONFIG="${MAP_SIM_POINTCEPT_CONFIG:-$POINTCEPT_DIR/configs/nuscenes/semseg-pt-v3m1-0-base.py}"
POINTCEPT_WEIGHT="${MAP_SIM_POINTCEPT_WEIGHT:-$POINTCEPT_DIR/weights/pointcept/nuscenes-semseg-pt-v3m1-0-base/model_best.pth}"
POINTCEPT_RUNTIME_ROOT="${MAP_SIM_POINTCEPT_RUNTIME_ROOT:-/tmp/pointcept_street_infer}"
BOOT_DELAY="${MAP_SIM_STREET_INFER_BOOT_DELAY:-12}"
ROS_HOME_DIR="${MAP_SIM_ROS_HOME:-$ROOT_DIR/.ros}"
ROS_LOG_DIR_PATH="${MAP_SIM_ROS_LOG_DIR:-$ROOT_DIR/log/ros}"

SIM_PID=""
INFER_PID=""

cleanup() {
  local pid
  for pid in "$INFER_PID" "$SIM_PID"; do
    [ -n "$pid" ] || continue
    kill -INT "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in "$INFER_PID" "$SIM_PID"; do
    [ -n "$pid" ] || continue
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

if [ ! -d "$POINTCEPT_ENV" ]; then
  echo "[ERR] Missing Pointcept env: $POINTCEPT_ENV"
  exit 1
fi

if [ ! -f "$POINTCEPT_CONFIG" ]; then
  echo "[ERR] Missing Pointcept config: $POINTCEPT_CONFIG"
  exit 1
fi

if [ ! -f "$POINTCEPT_WEIGHT" ]; then
  echo "[ERR] Missing Pointcept weight: $POINTCEPT_WEIGHT"
  echo "[ERR] Download the official weight before running street_infer."
  exit 1
fi

mkdir -p "$ROS_HOME_DIR" "$ROS_LOG_DIR_PATH"
export ROS_HOME="$ROS_HOME_DIR"
export ROS_LOG_DIR="$ROS_LOG_DIR_PATH"

MAP_SIM_ENABLE_DEFAULT_STACK=0 \
MAP_SIM_ENABLE_ELEVATION_MAPPING="${MAP_SIM_ENABLE_ELEVATION_MAPPING:-0}" \
MAP_SIM_ENABLE_MPPI_NAVIGATION="${MAP_SIM_ENABLE_MPPI_NAVIGATION:-0}" \
MAP_SIM_ENABLE_FASTLIO2="${MAP_SIM_ENABLE_FASTLIO2:-0}" \
MAP_SIM_ENABLE_POINTCLOUD_PIPELINE="${MAP_SIM_ENABLE_POINTCLOUD_PIPELINE:-1}" \
MAP_SIM_POINTCLOUD_PUBLISH_WORLD="${MAP_SIM_POINTCLOUD_PUBLISH_WORLD:-1}" \
MAP_SIM_POINTCLOUD_WORLD_TOPIC="${MAP_SIM_POINTCLOUD_WORLD_TOPIC:-/cloud_registered}" \
bash "$ROOT_DIR/scripts/run_sim.sh" street "$@" &
SIM_PID=$!

sleep "$BOOT_DELAY"

set +u
source /home/charles/miniconda3/etc/profile.d/conda.sh
conda activate "$POINTCEPT_ENV"
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/install/setup.bash"
set -u

export MAP_SIM_ROOT_DIR="$ROOT_DIR"
export MAP_SIM_POINTCEPT_ROOT="$POINTCEPT_DIR"
export MAP_SIM_POINTCEPT_RUNTIME_ROOT="$POINTCEPT_RUNTIME_ROOT"
export PYTHONNOUSERSITE=1

python "$ROOT_DIR/src/nexus_semantics/scripts/pointcept_semseg_node.py" \
  --ros-args \
  -p "input_topic:=${MAP_SIM_POINTCEPT_INPUT_TOPIC:-/cloud_registered}" \
  -p "output_topic:=${MAP_SIM_POINTCEPT_OUTPUT_TOPIC:-/pointcept/semantic_cloud}" \
  -p "model_config:=$POINTCEPT_CONFIG" \
  -p "weight_path:=$POINTCEPT_WEIGHT" \
  -p "runtime_root:=$POINTCEPT_RUNTIME_ROOT" \
  -p "inference_period_sec:=${MAP_SIM_POINTCEPT_INFER_PERIOD_SEC:-1.0}" \
  -p "min_points:=${MAP_SIM_POINTCEPT_MIN_POINTS:-1500}" \
  -p "force_disable_flash:=${MAP_SIM_POINTCEPT_FORCE_DISABLE_FLASH:-true}" \
  -p "force_native_spconv:=${MAP_SIM_POINTCEPT_FORCE_NATIVE_SPCONV:-true}" \
  -p "max_patch_size_no_flash:=${MAP_SIM_POINTCEPT_MAX_PATCH_SIZE_NO_FLASH:-256}" &
INFER_PID=$!

wait "$SIM_PID"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ELEV_WS_DIR="${MAP_SIM_ELEV_WS_DIR:-$ROOT_DIR/tools/elevation_mapping_cupy_ros2_ws}"
GP_PID=""

cleanup() {
  if [ -n "$GP_PID" ]; then
    kill -INT "$GP_PID" 2>/dev/null || true
    wait "$GP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

MAP_SIM_ENABLE_DEFAULT_STACK=0 \
MAP_SIM_ENABLE_ELEVATION_MAPPING="${MAP_SIM_ENABLE_ELEVATION_MAPPING:-0}" \
MAP_SIM_ENABLE_MPPI_NAVIGATION="${MAP_SIM_ENABLE_MPPI_NAVIGATION:-0}" \
MAP_SIM_ENABLE_POINTCLOUD_PIPELINE="${MAP_SIM_ENABLE_POINTCLOUD_PIPELINE:-1}" \
MAP_SIM_POINTCLOUD_ACCUMULATE_WORLD="${MAP_SIM_POINTCLOUD_ACCUMULATE_WORLD:-1}" \
MAP_SIM_ENABLE_TF_PUB="${MAP_SIM_ENABLE_TF_PUB:-1}" \
MAP_SIM_TF_PUB_PUBLISH_NAV_TF="${MAP_SIM_TF_PUB_PUBLISH_NAV_TF:-0}" \
MAP_SIM_GP_INPUT_TOPIC="${MAP_SIM_GP_INPUT_TOPIC:-/cloud_registered_accum}" \
MAP_SIM_RVIZ_CONFIG="${MAP_SIM_RVIZ_CONFIG:-$ROOT_DIR/src/nexus_gp_mapping/config/nexus_gp_navigation.rviz}" \
bash "$ROOT_DIR/scripts/run_sim.sh" "$@" &
SIM_PID=$!

sleep 12

unset PYTHONHOME PYTHONPATH CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER CONDA_SHLVL CONDA_EXE CONDA_PYTHON_EXE _CE_CONDA _CE_M || true
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
set +u
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/install/setup.bash"
[ -f "$ELEV_WS_DIR/install/setup.bash" ] && source "$ELEV_WS_DIR/install/setup.bash"
set -u

gp_ros_args=(
  --ros-args
  -p "input_topic:=${MAP_SIM_GP_INPUT_TOPIC:-/cloud_registered_accum}"
  -p "frame_id:=${MAP_SIM_GP_FRAME_ID:-world}"
  -p "length_in_x:=${MAP_SIM_GP_LENGTH_X:-10.0}"
  -p "length_in_y:=${MAP_SIM_GP_LENGTH_Y:-10.0}"
  -p "global_length_in_x:=${MAP_SIM_GP_GLOBAL_LENGTH_X:-30.0}"
  -p "global_length_in_y:=${MAP_SIM_GP_GLOBAL_LENGTH_Y:-30.0}"
  -p "resolution:=${MAP_SIM_GP_RESOLUTION:-0.2}"
  -p "inducing_points:=${MAP_SIM_GP_INDUCING_POINTS:-500}"
  -p "max_sensor_range:=${MAP_SIM_GP_MAX_SENSOR_RANGE:-5.0}"
  -p "min_points:=${MAP_SIM_GP_MIN_POINTS:-200}"
  -p "process_period_sec:=${MAP_SIM_GP_PROCESS_PERIOD_SEC:-3.0}"
  -p "training_iterations:=${MAP_SIM_GP_TRAINING_ITERATIONS:-30}"
  -p "gp_training_steps:=${MAP_SIM_GP_TRAINING_STEPS:-60}"
  -p "robust_fit_iterations:=${MAP_SIM_GP_ROBUST_FIT_ITERATIONS:-3}"
  -p "ground_seed_cell_size:=${MAP_SIM_GP_GROUND_SEED_CELL_SIZE:-0.5}"
  -p "robust_residual_threshold:=${MAP_SIM_GP_ROBUST_RESIDUAL_THRESHOLD:-0.22}"
  -p "robust_sigma_multiplier:=${MAP_SIM_GP_ROBUST_SIGMA_MULTIPLIER:-0.35}"
  -p "ground_lower_margin:=${MAP_SIM_GP_GROUND_LOWER_MARGIN:-0.30}"
  -p "sigma_margin_cap:=${MAP_SIM_GP_SIGMA_MARGIN_CAP:-2.0}"
  -p "floating_reject_margin:=${MAP_SIM_GP_FLOATING_REJECT_MARGIN:-1.0}"
  -p "floating_connectivity_radius:=${MAP_SIM_GP_FLOATING_CONNECTIVITY_RADIUS:-0.45}"
)

if [ -n "${MAP_SIM_GP_CENTER_POSE_TOPIC:-}" ]; then
  gp_ros_args+=(-p "center_pose_topic:=${MAP_SIM_GP_CENTER_POSE_TOPIC}")
fi

ros2 run nexus_gp_mapping gp_mapping_node "${gp_ros_args[@]}" &
GP_PID=$!

wait "$SIM_PID"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ELEV_WS_DIR="${MAP_SIM_ELEV_WS_DIR:-/home/charles/NEXUS/tools/elevation_mapping_cupy_ros2_ws}"
ELEV_PID=""
EXPORT_PID=""
TRAV_MAP_PID=""
EXPLORER_PID=""
MPPI_PID=""
SAND_MPC_PID=""
SIM_PID=""
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"

sanitize_python_env() {
  unset PYTHONHOME PYTHONPATH CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER CONDA_SHLVL CONDA_EXE CONDA_PYTHON_EXE _CE_CONDA _CE_M || true
  export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
  if [ -n "${LD_LIBRARY_PATH:-}" ]; then
    local sanitized_ld=""
    sanitized_ld="$(printf '%s' "$LD_LIBRARY_PATH" \
      | tr ':' '\n' \
      | awk 'NF && $0 !~ /(mini)?conda/ && !seen[$0]++' \
      | paste -sd: -)"
    if [ -n "$sanitized_ld" ]; then
      export LD_LIBRARY_PATH="$sanitized_ld"
    else
      unset LD_LIBRARY_PATH || true
    fi
  fi
  hash -r || true
}

prepend_path_once() {
  local var_name="$1"
  local dir_path="$2"
  if [ ! -d "$dir_path" ]; then
    return 0
  fi

  local current_value="${!var_name:-}"
  case ":$current_value:" in
    *":$dir_path:"*) ;;
    *)
      if [ -n "$current_value" ]; then
        export "$var_name=$dir_path:$current_value"
      else
        export "$var_name=$dir_path"
      fi
      ;;
  esac
}

append_python_cuda_lib_paths() {
  local pyver
  pyver="$("/usr/bin/python3" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

  local roots=(
    "$HOME/.local/lib/python${pyver}/site-packages"
    "/usr/local/lib/python${pyver}/dist-packages"
  )

  local root dir
  for root in "${roots[@]}"; do
    [ -d "$root" ] || continue
    for dir in "$root"/nvidia/*/lib "$root"/torch/lib; do
      [ -d "$dir" ] || continue
      prepend_path_once LD_LIBRARY_PATH "$dir"
    done
  done
}

wait_for_sim_startup_or_exit() {
  local delay_seconds="${1%.*}"
  [ -n "$delay_seconds" ] || delay_seconds=0
  local deadline=$((SECONDS + delay_seconds))

  while (( SECONDS < deadline )); do
    if ! kill -0 "$SIM_PID" 2>/dev/null; then
      local status=0
      wait "$SIM_PID" || status=$?
      if [ "$status" -eq 0 ]; then
        echo "[ERR] Base simulation exited unexpectedly before dependent nodes were started."
        return 1
      fi
      return "$status"
    fi
    sleep 1
  done

  if ! kill -0 "$SIM_PID" 2>/dev/null; then
    local status=0
    wait "$SIM_PID" || status=$?
    if [ "$status" -eq 0 ]; then
      echo "[ERR] Base simulation exited unexpectedly during dependent-node startup."
      return 1
    fi
    return "$status"
  fi
}

cleanup() {
  local pid
  for pid in "$EXPLORER_PID" "$SAND_MPC_PID" "$MPPI_PID" "$TRAV_MAP_PID" "$EXPORT_PID" "$ELEV_PID" "$SIM_PID"; do
    [ -n "$pid" ] || continue
    kill -INT "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in "$EXPLORER_PID" "$SAND_MPC_PID" "$MPPI_PID" "$TRAV_MAP_PID" "$EXPORT_PID" "$ELEV_PID" "$SIM_PID"; do
    [ -n "$pid" ] || continue
    kill "$pid" 2>/dev/null || true
  done
  for pid in "$EXPLORER_PID" "$SAND_MPC_PID" "$MPPI_PID" "$TRAV_MAP_PID" "$EXPORT_PID" "$ELEV_PID" "$SIM_PID"; do
    [ -n "$pid" ] || continue
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

MAP_SIM_STACK_CONFIG="${MAP_SIM_STACK_CONFIG:-$ROOT_DIR/config/nexus_navigation_stack.yaml}"
MAP_SIM_ELEVATION_CONFIG="${MAP_SIM_ELEVATION_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_EXPORTER_CONFIG="${MAP_SIM_EXPORTER_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_TRAVERSABILITY_CONFIG="${MAP_SIM_TRAVERSABILITY_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_MPPI_CONFIG="${MAP_SIM_MPPI_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_SAND_MPC_CONFIG="${MAP_SIM_SAND_MPC_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_EXPLORER_CONFIG="${MAP_SIM_EXPLORER_CONFIG:-$MAP_SIM_STACK_CONFIG}"
MAP_SIM_MPPI_BOOT_DELAY="${MAP_SIM_MPPI_BOOT_DELAY:-10}"
MAP_SIM_ENABLE_SAND_MPC="${MAP_SIM_ENABLE_SAND_MPC:-1}"
MAP_SIM_ENABLE_NOVELTY_EXPLORATION="${MAP_SIM_ENABLE_NOVELTY_EXPLORATION:-1}"
FASTLIO_ENABLED="${MAP_SIM_ENABLE_FASTLIO2:-0}"
MAP_SIM_ELEVATION_OUTPUT_DIR="${MAP_SIM_ELEVATION_OUTPUT_DIR:-$ROOT_DIR/output/elevation_maps/$RUN_STAMP}"
MAP_SIM_ELEV_ROBOT_CONFIG="${MAP_SIM_ELEV_ROBOT_CONFIG:-}"

for config_path in \
  "$MAP_SIM_STACK_CONFIG" \
  "$MAP_SIM_ELEVATION_CONFIG" \
  "$MAP_SIM_EXPORTER_CONFIG" \
  "$MAP_SIM_TRAVERSABILITY_CONFIG" \
  "$MAP_SIM_MPPI_CONFIG" \
  "$MAP_SIM_SAND_MPC_CONFIG" \
  "$MAP_SIM_EXPLORER_CONFIG"; do
  if [ ! -f "$config_path" ]; then
    echo "[ERR] Missing config: $config_path"
    exit 1
  fi
done

if [ -n "$MAP_SIM_ELEV_ROBOT_CONFIG" ] && [ ! -f "$MAP_SIM_ELEV_ROBOT_CONFIG" ]; then
  echo "[ERR] Missing elevation override config: $MAP_SIM_ELEV_ROBOT_CONFIG"
  exit 1
fi

mkdir -p "$MAP_SIM_ELEVATION_OUTPUT_DIR"
echo "[INFO] Elevation map artifacts will be written to: $MAP_SIM_ELEVATION_OUTPUT_DIR"
echo "[INFO] Unified stack config: $MAP_SIM_STACK_CONFIG"

if [ ! -f "$ELEV_WS_DIR/install/setup.bash" ]; then
  echo "[INFO] elevation_mapping_cupy ROS2 workspace not built yet, building now..."
  bash "$ROOT_DIR/tools/elevation_ros2/build_elevation_mapping_ros2.sh"
fi

MAP_SIM_INTERNAL_MPPI_NAVIGATION=1 \
MAP_SIM_INTERNAL_ELEVATION_LAUNCH=1 \
MAP_SIM_ENABLE_DEFAULT_STACK=0 \
MAP_SIM_ENABLE_ELEVATION_MAPPING=1 \
MAP_SIM_ENABLE_FASTLIO2="${MAP_SIM_ENABLE_FASTLIO2:-0}" \
MAP_SIM_ENABLE_POINTCLOUD_PIPELINE="${MAP_SIM_ENABLE_POINTCLOUD_PIPELINE:-1}" \
MAP_SIM_ENABLE_TF_PUB="${MAP_SIM_ENABLE_TF_PUB:-1}" \
MAP_SIM_TF_PUB_PUBLISH_NAV_TF="${MAP_SIM_TF_PUB_PUBLISH_NAV_TF:-0}" \
bash "$ROOT_DIR/scripts/run_sim.sh" "$@" &
SIM_PID=$!

wait_for_sim_startup_or_exit "$MAP_SIM_MPPI_BOOT_DELAY"

sanitize_python_env
set +u
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/install/setup.bash"
[ -f "$ELEV_WS_DIR/install/setup.bash" ] && source "$ELEV_WS_DIR/install/setup.bash"
set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
export PYTHONPATH="$ROOT_DIR/tools/elevation_ros2/python${PYTHONPATH:+:$PYTHONPATH}"
append_python_cuda_lib_paths

EXPORT_ARGS=(
  --ros-args
  --params-file "$MAP_SIM_EXPORTER_CONFIG"
  -p "output_dir:=$MAP_SIM_ELEVATION_OUTPUT_DIR"
)
if [ -n "${MAP_SIM_ELEVATION_TOPIC:-}" ]; then
  EXPORT_ARGS+=(-p "grid_map_topic:=${MAP_SIM_ELEVATION_TOPIC}")
fi
if [ -n "${MAP_SIM_ELEVATION_SAVE_INTERVAL:-}" ]; then
  EXPORT_ARGS+=(-p "save_interval_sec:=${MAP_SIM_ELEVATION_SAVE_INTERVAL}")
fi

/usr/bin/python3 "$ROOT_DIR/src/nexus_elevation_mppi/scripts/elevation_map_exporter.py" \
  "${EXPORT_ARGS[@]}" &
EXPORT_PID=$!

TRAV_ARGS=(
  --ros-args
  --params-file "$MAP_SIM_TRAVERSABILITY_CONFIG"
)
if [ -n "${MAP_SIM_ELEVATION_TOPIC:-}" ]; then
  TRAV_ARGS+=(-p "grid_map_topic:=${MAP_SIM_ELEVATION_TOPIC}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_MAP_TOPIC:-}" ]; then
  TRAV_ARGS+=(-p "map_topic:=${MAP_SIM_TRAVERSABILITY_MAP_TOPIC}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_LAYER:-}" ]; then
  TRAV_ARGS+=(-p "layer:=${MAP_SIM_TRAVERSABILITY_LAYER}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_FRAME_ID:-}" ]; then
  TRAV_ARGS+=(-p "frame_id:=${MAP_SIM_TRAVERSABILITY_FRAME_ID}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_FALLBACK_FRAME_ID:-}" ]; then
  TRAV_ARGS+=(-p "fallback_frame_id:=${MAP_SIM_TRAVERSABILITY_FALLBACK_FRAME_ID}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_KERNEL_SIZE:-}" ]; then
  TRAV_ARGS+=(-p "kernel_size:=${MAP_SIM_TRAVERSABILITY_KERNEL_SIZE}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_CLEAR_BELOW_M:-}" ]; then
  TRAV_ARGS+=(-p "clear_below_m:=${MAP_SIM_TRAVERSABILITY_CLEAR_BELOW_M}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_ACCUMULATE_FROM_M:-}" ]; then
  TRAV_ARGS+=(-p "accumulate_from_m:=${MAP_SIM_TRAVERSABILITY_ACCUMULATE_FROM_M}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_FULL_AT_M:-}" ]; then
  TRAV_ARGS+=(-p "full_at_m:=${MAP_SIM_TRAVERSABILITY_FULL_AT_M}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_MEDIAN_FILTER_SIZE:-}" ]; then
  TRAV_ARGS+=(-p "median_filter_size:=${MAP_SIM_TRAVERSABILITY_MEDIAN_FILTER_SIZE}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_GAUSSIAN_FILTER_SIZE:-}" ]; then
  TRAV_ARGS+=(-p "gaussian_filter_size:=${MAP_SIM_TRAVERSABILITY_GAUSSIAN_FILTER_SIZE}")
fi
if [ -n "${MAP_SIM_TRAVERSABILITY_GAUSSIAN_SIGMA:-}" ]; then
  TRAV_ARGS+=(-p "gaussian_sigma:=${MAP_SIM_TRAVERSABILITY_GAUSSIAN_SIGMA}")
fi

/usr/bin/python3 "$ROOT_DIR/src/nexus_elevation_mppi/scripts/traversability_to_map.py" \
  "${TRAV_ARGS[@]}" &
TRAV_MAP_PID=$!

ELEV_ARGS=(
  --ros-args
  --params-file "$MAP_SIM_ELEVATION_CONFIG"
)
if [ -n "$MAP_SIM_ELEV_ROBOT_CONFIG" ]; then
  ELEV_ARGS+=(--params-file "$MAP_SIM_ELEV_ROBOT_CONFIG")
fi
if [ "$FASTLIO_ENABLED" = "1" ]; then
  ELEV_ARGS+=(-p "subscribers.lidar.topic_name:=/fastlio2/world_cloud")
fi

ros2 run elevation_mapping_cupy elevation_mapping_node.py \
  "${ELEV_ARGS[@]}" &
ELEV_PID=$!

# --- Nav2 MPPI controller (replaces custom mppi_navigator) ---
# Uses the official nav2_mppi_controller with Omni motion model.
# Parameters mirror the prior custom config (see config/nav2_mppi_params.yaml).
# The /goal_pose -> NavigateToPose bridge is included in the launch file.
#
# cmd_vel routing:
#   Sand MPC ON:  Nav2 -> /mppi/cmd_vel_raw -> sand_mpc -> /cmd_vel -> cmd_vel_to_swerve
#   Sand MPC OFF: Nav2 -> /cmd_vel -> cmd_vel_to_swerve
export MAP_SIM_ROOT="$ROOT_DIR"
NAV2_PARAMS_FILE="${MAP_SIM_NAV2_PARAMS:-$ROOT_DIR/config/nav2_mppi_params.yaml}"

if [ "$MAP_SIM_ENABLE_SAND_MPC" = "1" ]; then
  NAV2_CMD_VEL="/mppi/cmd_vel_raw"
else
  NAV2_CMD_VEL="/cmd_vel"
fi

ros2 launch "$ROOT_DIR/launch/nav2_mppi.launch.py" \
  use_sim_time:=true \
  params_file:="$NAV2_PARAMS_FILE" \
  cmd_vel_topic:="$NAV2_CMD_VEL" &
MPPI_PID=$!
echo "[INFO] Nav2 MPPI controller launched (PID=$MPPI_PID, cmd_vel=$NAV2_CMD_VEL)."

if [ "$MAP_SIM_ENABLE_SAND_MPC" = "1" ]; then
  echo "[INFO] Launching sand MPC compensator (/mppi/cmd_vel_raw -> /cmd_vel)."
  ros2 run nexus_sand_mpc sand_mpc_compensator \
    --ros-args \
    --params-file "$MAP_SIM_SAND_MPC_CONFIG" &
  SAND_MPC_PID=$!
else
  echo "[INFO] Sand MPC disabled (MAP_SIM_ENABLE_SAND_MPC=$MAP_SIM_ENABLE_SAND_MPC); Nav2 publishes directly to /cmd_vel."
fi

if [ "$MAP_SIM_ENABLE_NOVELTY_EXPLORATION" = "1" ]; then
  echo "[INFO] Launching novelty explorer (height-difference map -> radar_known -> MPPI goal/path)."
  ros2 run nexus_elevation_mppi novelty_explorer \
    --ros-args \
    --params-file "$MAP_SIM_EXPLORER_CONFIG" &
  EXPLORER_PID=$!
else
  echo "[INFO] Novelty exploration disabled (MAP_SIM_ENABLE_NOVELTY_EXPLORATION=$MAP_SIM_ENABLE_NOVELTY_EXPLORATION)."
fi

wait "$SIM_PID"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS_DIR="$ROOT_DIR/ws"

if [ -f "$ROOT_DIR/runlocal/gpu_gl_env.sh" ]; then
  source "$ROOT_DIR/runlocal/gpu_gl_env.sh"
  apply_map_sim_gpu_gl_defaults
fi

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

detect_software_gl_renderer() {
  if ! command -v glxinfo >/dev/null 2>&1; then
    return 1
  fi

  local glxinfo_output=""
  if command -v timeout >/dev/null 2>&1; then
    glxinfo_output="$(timeout 2s glxinfo -B 2>/dev/null || true)"
  else
    glxinfo_output="$(glxinfo -B 2>/dev/null || true)"
  fi

  if [ -z "$glxinfo_output" ]; then
    return 1
  fi

  printf '%s\n' "$glxinfo_output" | grep -qiE 'OpenGL renderer string:.*llvmpipe|Accelerated:[[:space:]]*no'
}

apply_safe_gui_defaults() {
  export MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}"
  export MAP_SIM_SOFTWARE_GL_DETECTED=0

  if [ "$MAP_SIM_GZCLIENT" != "1" ]; then
    return 0
  fi

  if detect_software_gl_renderer; then
    export MAP_SIM_SOFTWARE_GL_DETECTED=1
    echo "[WARN] OpenGL renderer is using software rendering (llvmpipe / Accelerated: no)."
    echo "[WARN] If the machine freezes, rerun with MAP_SIM_GZCLIENT=0."
  fi
}

resolve_world_from_map_id() {
  case "$1" in
    1) echo "rm_2026_slam_world.world" ;;
    2) echo "apollo15_map_only.world" ;;
    3) echo "marsyard2020_map_only.world" ;;
    4) echo "marsyard2021_map_only.world" ;;
    5) echo "marsyard2022_map_only.world" ;;
    6) echo "mars_gazebo_topography_map_only.world" ;;
    7|showcase) echo "space_maps_showcase.world" ;;
    8|cave|ltu_cave) echo "darpa_cave_01.world" ;;
    *) return 1 ;;
  esac
}

print_map_menu() {
  cat <<'MAPS_EOF'
[MAPS]
  1 -> rm_2026_slam_world.world
  2 -> apollo15_map_only.world
  3 -> marsyard2020_map_only.world
  4 -> marsyard2021_map_only.world
  5 -> marsyard2022_map_only.world
  6 -> mars_gazebo_topography_map_only.world
  7 -> space_maps_showcase.world
  8 -> darpa_cave_01.world
MAPS_EOF
}

apply_default_spawn_for_world() {
  local world
  world="$(basename "$1")"
  local default_x="0.0"
  local default_y="0.0"
  local default_z="0.5"

  case "$world" in
    rm_2026_slam_world.world)
      default_z="0.19" ;;
    apollo15_map_only.world)
      default_z="0.85" ;;
    marsyard2020_map_only.world)
      default_z="1.60" ;;
    marsyard2021_map_only.world)
      default_z="2.90" ;;
    marsyard2022_map_only.world)
      default_z="2.20" ;;
    mars_gazebo_topography_map_only.world)
      default_z="18.0" ;;
    space_maps_showcase.world)
      default_z="0.85" ;;
    darpa_cave_01.world)
      default_z="0.42" ;;
  esac

  export MAP_SIM_SPAWN_X="${MAP_SIM_SPAWN_X:-$default_x}"
  export MAP_SIM_SPAWN_Y="${MAP_SIM_SPAWN_Y:-$default_y}"
  export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-$default_z}"
}

apply_default_livox_profile_for_world() {
  local world
  world="$(basename "$1")"
  local default_samples="20000"
  local default_downsample="1"
  local default_max_range="70.0"

  case "$world" in
    darpa_cave_01.world)
      default_samples="24000"
      default_max_range="42.0"
      ;;
  esac

  export MAP_SIM_LIVOX_SAMPLES="${MAP_SIM_LIVOX_SAMPLES:-$default_samples}"
  export MAP_SIM_LIVOX_DOWNSAMPLE="${MAP_SIM_LIVOX_DOWNSAMPLE:-$default_downsample}"
  export MAP_SIM_LIVOX_MAX_RANGE="${MAP_SIM_LIVOX_MAX_RANGE:-$default_max_range}"
}

apply_default_lighting_profile_for_world() {
  local world
  world="$(basename "$1")"

  if [ "${MAP_SIM_SOLAR_TIME_WAS_SET}" = "0" ]; then
    if [ "$world" = "darpa_cave_01.world" ]; then
      export MAP_SIM_SOLAR_TIME=""
    else
      export MAP_SIM_SOLAR_TIME="12:00"
    fi
  fi

  if [ "${MAP_SIM_ENABLE_SOLAR_TIME_PANEL_WAS_SET}" = "0" ]; then
    if [ "$world" = "darpa_cave_01.world" ]; then
      export MAP_SIM_ENABLE_SOLAR_TIME_PANEL=0
    else
      export MAP_SIM_ENABLE_SOLAR_TIME_PANEL=1
    fi
  fi
}

[ -f /opt/ros/humble/setup.bash ] || {
  echo "[ERR] Missing /opt/ros/humble/setup.bash"
  exit 1
}
[ -f "$WS_DIR/install/setup.bash" ] || {
  echo "[ERR] Missing $WS_DIR/install/setup.bash"
  echo "[HINT] Build the workspace first: bash ./build_local.sh"
  exit 1
}

sanitize_python_env
set +u
source /opt/ros/humble/setup.bash
source "$WS_DIR/install/setup.bash"
set -u

export MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}"
export MAP_SIM_ENABLE_HEADLESS_RENDERING="${MAP_SIM_ENABLE_HEADLESS_RENDERING:-0}"
export MAP_SIM_SPAWN_ROBOT="${MAP_SIM_SPAWN_ROBOT:-1}"
export MAP_SIM_ENABLE_LIVOX="${MAP_SIM_ENABLE_LIVOX:-1}"
export MAP_SIM_ENABLE_DEPTH_CAMERA="${MAP_SIM_ENABLE_DEPTH_CAMERA:-0}"
export MAP_SIM_ENABLE_IMU="${MAP_SIM_ENABLE_IMU:-1}"
export MAP_SIM_ENABLE_TF_PUB="${MAP_SIM_ENABLE_TF_PUB:-0}"
export MAP_SIM_ENABLE_RVIZ="${MAP_SIM_ENABLE_RVIZ:-${MAP_SIM_GZCLIENT}}"
export MAP_SIM_ENABLE_ROS2_CONTROL="${MAP_SIM_ENABLE_ROS2_CONTROL:-1}"
export MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA="${MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA:-${MAP_SIM_ALLOW_UNSTABLE_HEADLESS_DEPTH_CAMERA:-0}}"
export MAP_SIM_LIGHTING_PRESET="${MAP_SIM_LIGHTING_PRESET:-world}"
export MAP_SIM_LIGHTING_BRIGHTNESS="${MAP_SIM_LIGHTING_BRIGHTNESS:-1.0}"
export MAP_SIM_RVIZ_CONFIG="${MAP_SIM_RVIZ_CONFIG:-}"
export MAP_SIM_DEPTH_CAMERA_NAME="${MAP_SIM_DEPTH_CAMERA_NAME:-livox_tilt_depth}"
export MAP_SIM_DEPTH_CAMERA_TOPIC_PREFIX="${MAP_SIM_DEPTH_CAMERA_TOPIC_PREFIX:-livox/depth}"
export MAP_SIM_DEPTH_CAMERA_FRAME_NAME="${MAP_SIM_DEPTH_CAMERA_FRAME_NAME:-depth_camera_mount_link}"
export MAP_SIM_DEPTH_CAMERA_UPDATE_RATE="${MAP_SIM_DEPTH_CAMERA_UPDATE_RATE:-60.0}"
export MAP_SIM_DEPTH_CAMERA_WIDTH="${MAP_SIM_DEPTH_CAMERA_WIDTH:-848}"
export MAP_SIM_DEPTH_CAMERA_HEIGHT="${MAP_SIM_DEPTH_CAMERA_HEIGHT:-480}"
export MAP_SIM_DEPTH_CAMERA_HFOV="${MAP_SIM_DEPTH_CAMERA_HFOV:-1.5184364}"
export MAP_SIM_DEPTH_CAMERA_NEAR_CLIP="${MAP_SIM_DEPTH_CAMERA_NEAR_CLIP:-0.10}"
export MAP_SIM_DEPTH_CAMERA_FAR_CLIP="${MAP_SIM_DEPTH_CAMERA_FAR_CLIP:-10.0}"
export MAP_SIM_DEPTH_CAMERA_MIN_DEPTH="${MAP_SIM_DEPTH_CAMERA_MIN_DEPTH:-0.10}"
export MAP_SIM_DEPTH_CAMERA_MAX_DEPTH="${MAP_SIM_DEPTH_CAMERA_MAX_DEPTH:-10.0}"
export MAP_SIM_DEPTH_CAMERA_VISUALIZE="${MAP_SIM_DEPTH_CAMERA_VISUALIZE:-0}"
export MAP_SIM_RUNTIME_DEPTH_TARGET_MODEL="${MAP_SIM_RUNTIME_DEPTH_TARGET_MODEL:-cube_robot}"
export MAP_SIM_RUNTIME_DEPTH_TARGET_LINK="${MAP_SIM_RUNTIME_DEPTH_TARGET_LINK:-depth_camera_mount_link}"

MAP_SIM_SOLAR_TIME_WAS_SET=0
if [ "${MAP_SIM_SOLAR_TIME+x}" = "x" ]; then
  MAP_SIM_SOLAR_TIME_WAS_SET=1
fi
export MAP_SIM_SOLAR_TIME="${MAP_SIM_SOLAR_TIME:-}"

MAP_SIM_ENABLE_SOLAR_TIME_PANEL_WAS_SET=0
if [ "${MAP_SIM_ENABLE_SOLAR_TIME_PANEL+x}" = "x" ]; then
  MAP_SIM_ENABLE_SOLAR_TIME_PANEL_WAS_SET=1
fi
export MAP_SIM_ENABLE_SOLAR_TIME_PANEL="${MAP_SIM_ENABLE_SOLAR_TIME_PANEL:-1}"

apply_safe_gui_defaults

if [ "${MAP_SIM_ENABLE_RVIZ}" = "1" ] && [ -z "${DISPLAY:-}" ]; then
  echo "[WARN] MAP_SIM_ENABLE_RVIZ=1 but DISPLAY is empty."
  echo "[WARN] rviz2 may fail to open unless an X11 / desktop session is available."
fi

if [ "${MAP_SIM_ENABLE_DEPTH_CAMERA}" = "1" ] \
  && [ "${MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA}" != "1" ]; then
  echo "[ERR] Depth camera support is preserved, but enabling /livox/depth/* is currently unstable"
  echo "[ERR] in this Gazebo Classic stack and can crash gzserver/gzclient."
  echo "[HINT] Keep MAP_SIM_ENABLE_DEPTH_CAMERA=0 for the stable bare sim."
  echo "[HINT] Set MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA=1 if you still want to test it."
  exit 1
fi

if [ "${MAP_SIM_FORCE_CLEAN_START:-1}" = "1" ]; then
  echo "[INFO] Clean start: clearing stale Gazebo processes"
  "$ROOT_DIR/runlocal/stop.sh" --keep-rviz
fi

export LIVOX_SIM_ROOT="$WS_DIR/src/ros2_livox_simulation"
cd "$WS_DIR"

if command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q :11345; then
  echo "[ERR] Gazebo master port 11345 is already in use."
  echo "[HINT] Run ./runlocal/stop.sh to clear old Gazebo processes, then rerun."
  exit 1
fi

MAP_SELECTOR="${1:-${MAP_SIM_MAP:-}}"
if [ -n "$MAP_SELECTOR" ]; then
  if WORLD_FROM_ID="$(resolve_world_from_map_id "$MAP_SELECTOR" 2>/dev/null)"; then
    export MAP_SIM_WORLD="$WORLD_FROM_ID"
  elif [ -z "${MAP_SIM_WORLD:-}" ]; then
    echo "[ERR] Unknown map selector: $MAP_SELECTOR"
    print_map_menu
    exit 1
  fi
fi

export MAP_SIM_WORLD="${MAP_SIM_WORLD:-marsyard2020_map_only.world}"
apply_default_spawn_for_world "$MAP_SIM_WORLD"
apply_default_livox_profile_for_world "$MAP_SIM_WORLD"
apply_default_lighting_profile_for_world "$MAP_SIM_WORLD"

BASE_VARIANT="${MAP_SIM_BASE_VARIANT:-omni}"
case "$BASE_VARIANT" in
  omni|swerve)
    LAUNCH_FILE="sim_launch_omni.py"
    VARIANT_LABEL="omni"
    EXTRA_ARGS=()
    ;;
  classic|legacy)
    LAUNCH_FILE="sim_launch.py"
    VARIANT_LABEL="classic"
    EXTRA_ARGS=("enable_ros2_control:=${MAP_SIM_ENABLE_ROS2_CONTROL}")
    ;;
  *)
    echo "[ERR] Unsupported MAP_SIM_BASE_VARIANT=${BASE_VARIANT}"
    echo "[HINT] Supported values: omni, swerve, classic, legacy"
    exit 1
    ;;
esac

if [ "${MAP_SIM_GZCLIENT}" = "1" ]; then
  echo "[INFO] Launch mode: GUI"
else
  echo "[INFO] Launch mode: headless"
fi
echo "[INFO] Variant: ${VARIANT_LABEL}"
echo "[INFO] World: ${MAP_SIM_WORLD}"
echo "[INFO] Spawn robot: ${MAP_SIM_SPAWN_ROBOT}"
echo "[INFO] Spawn pose: x=${MAP_SIM_SPAWN_X} y=${MAP_SIM_SPAWN_Y} z=${MAP_SIM_SPAWN_Z}"
echo "[INFO] Livox sensor: ${MAP_SIM_ENABLE_LIVOX}"
echo "[INFO] Depth camera: ${MAP_SIM_ENABLE_DEPTH_CAMERA}"
echo "[INFO] IMU: ${MAP_SIM_ENABLE_IMU}"
echo "[INFO] RViz: ${MAP_SIM_ENABLE_RVIZ}"
echo "[INFO] Lighting: preset=${MAP_SIM_LIGHTING_PRESET} brightness=${MAP_SIM_LIGHTING_BRIGHTNESS}"
if [ -n "${MAP_SIM_SOLAR_TIME}" ]; then
  echo "[INFO] Solar lighting: enabled initial_time=${MAP_SIM_SOLAR_TIME} live_panel=${MAP_SIM_ENABLE_SOLAR_TIME_PANEL}"
else
  echo "[INFO] Solar lighting: disabled"
fi
print_map_menu

LAUNCH_ARGS=(
  "world_name:=${MAP_SIM_WORLD}"
  "use_gui:=${MAP_SIM_GZCLIENT}"
  "enable_headless_rendering:=${MAP_SIM_ENABLE_HEADLESS_RENDERING}"
  "spawn_robot:=${MAP_SIM_SPAWN_ROBOT}"
  "spawn_x:=${MAP_SIM_SPAWN_X}"
  "spawn_y:=${MAP_SIM_SPAWN_Y}"
  "spawn_z:=${MAP_SIM_SPAWN_Z}"
  "enable_livox:=${MAP_SIM_ENABLE_LIVOX}"
  "enable_depth_camera:=${MAP_SIM_ENABLE_DEPTH_CAMERA}"
  "enable_imu:=${MAP_SIM_ENABLE_IMU}"
  "enable_tf_pub:=${MAP_SIM_ENABLE_TF_PUB}"
  "enable_rviz:=${MAP_SIM_ENABLE_RVIZ}"
  "lighting_preset:=${MAP_SIM_LIGHTING_PRESET}"
  "lighting_brightness:=${MAP_SIM_LIGHTING_BRIGHTNESS}"
  "solar_time:=${MAP_SIM_SOLAR_TIME}"
  "enable_solar_time_panel:=${MAP_SIM_ENABLE_SOLAR_TIME_PANEL}"
  "livox_samples:=${MAP_SIM_LIVOX_SAMPLES}"
  "livox_downsample:=${MAP_SIM_LIVOX_DOWNSAMPLE}"
  "livox_max_range:=${MAP_SIM_LIVOX_MAX_RANGE}"
)

if [ -n "${MAP_SIM_RVIZ_CONFIG}" ]; then
  LAUNCH_ARGS+=("rviz_config:=${MAP_SIM_RVIZ_CONFIG}")
fi

LAUNCH_ARGS+=("${EXTRA_ARGS[@]}")

exec ros2 launch ros2_livox_simulation "$LAUNCH_FILE" "${LAUNCH_ARGS[@]}"

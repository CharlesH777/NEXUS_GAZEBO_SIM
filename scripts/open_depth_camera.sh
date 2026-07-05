#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="$ROOT_DIR"
PY_SCRIPT="$WS_DIR/src/ros2_livox_simulation/scripts/runtime_depth_camera.py"

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

usage() {
  cat <<'EOF'
Usage:
  ./open_depth_camera.sh
  ./open_depth_camera.sh --stop
  ./open_depth_camera.sh --status

Default behavior:
  Spawn a standalone runtime depth camera after ./scripts/run_sim.sh is already running.

Environment overrides:
  MAP_SIM_DEPTH_CAMERA_NAME
  MAP_SIM_DEPTH_CAMERA_TOPIC_PREFIX
  MAP_SIM_DEPTH_CAMERA_FRAME_NAME
  MAP_SIM_DEPTH_CAMERA_UPDATE_RATE
  MAP_SIM_DEPTH_CAMERA_WIDTH / HEIGHT / HFOV
  MAP_SIM_DEPTH_CAMERA_NEAR_CLIP / FAR_CLIP / MIN_DEPTH / MAX_DEPTH
  MAP_SIM_DEPTH_CAMERA_VISUALIZE
  MAP_SIM_RUNTIME_DEPTH_TARGET_MODEL
  MAP_SIM_RUNTIME_DEPTH_TARGET_LINK
EOF
}

run_camera_tool() {
  sanitize_python_env
  set +u
  source /opt/ros/humble/setup.bash
  source "$ROOT_DIR/install/setup.bash"
  set -u

  local visualize_arg=()
  if [ "${MAP_SIM_DEPTH_CAMERA_VISUALIZE:-0}" = "1" ]; then
    visualize_arg=(--visualize)
  fi

  python3 "$PY_SCRIPT" \
    --camera-name "${MAP_SIM_DEPTH_CAMERA_NAME:-livox_tilt_depth}" \
    --target-model-name "${MAP_SIM_RUNTIME_DEPTH_TARGET_MODEL:-cube_robot}" \
    --target-link-name "${MAP_SIM_RUNTIME_DEPTH_TARGET_LINK:-depth_camera_mount_link}" \
    --topic-prefix "${MAP_SIM_DEPTH_CAMERA_TOPIC_PREFIX:-livox/depth}" \
    --frame-name "${MAP_SIM_DEPTH_CAMERA_FRAME_NAME:-depth_camera_mount_link}" \
    --update-rate "${MAP_SIM_DEPTH_CAMERA_UPDATE_RATE:-60.0}" \
    --width "${MAP_SIM_DEPTH_CAMERA_WIDTH:-848}" \
    --height "${MAP_SIM_DEPTH_CAMERA_HEIGHT:-480}" \
    --hfov "${MAP_SIM_DEPTH_CAMERA_HFOV:-1.5184364}" \
    --near-clip "${MAP_SIM_DEPTH_CAMERA_NEAR_CLIP:-0.10}" \
    --far-clip "${MAP_SIM_DEPTH_CAMERA_FAR_CLIP:-10.0}" \
    --min-depth "${MAP_SIM_DEPTH_CAMERA_MIN_DEPTH:-0.10}" \
    --max-depth "${MAP_SIM_DEPTH_CAMERA_MAX_DEPTH:-10.0}" \
    "${visualize_arg[@]}" \
    "$@"
}

ACTION="${1:-start}"
case "$ACTION" in
  start)
    run_camera_tool
    ;;
  --stop|stop)
    run_camera_tool --delete-only
    ;;
  --status|status)
    run_camera_tool --status-only
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "[ERR] Unknown argument: $ACTION"
    usage
    exit 1
    ;;
esac

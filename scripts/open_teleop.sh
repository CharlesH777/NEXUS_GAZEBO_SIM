#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="$ROOT_DIR"

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

if [ -z "${DISPLAY:-}" ]; then
  echo "[ERR] DISPLAY is empty. The teleop GUI needs a desktop/X11 session."
  exit 1
fi

sanitize_python_env
set +u
source /opt/ros/humble/setup.bash
source "$ROOT_DIR/install/setup.bash"
set -u

exec ros2 run nexus_teleop teleop_gui \
  --ros-args \
  -p cmd_vel_topic:="${MAP_SIM_TELEOP_TOPIC:-/cmd_vel}" \
  -p publish_rate:="${MAP_SIM_TELEOP_PUBLISH_RATE:-20.0}" \
  -p linear_speed:="${MAP_SIM_TELEOP_LINEAR_SPEED:-1.0}" \
  -p strafe_speed:="${MAP_SIM_TELEOP_STRAFE_SPEED:-1.0}" \
  -p angular_speed:="${MAP_SIM_TELEOP_ANGULAR_SPEED:-1.2}" \
  -p config_path:="${MAP_SIM_STACK_CONFIG:-$ROOT_DIR/config/nexus_navigation_stack.yaml}"

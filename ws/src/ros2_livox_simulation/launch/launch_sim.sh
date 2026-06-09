#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVOX_SIM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source /opt/ros/humble/setup.bash
source "$LIVOX_SIM_ROOT/../../install/setup.bash"

exec ros2 launch ros2_livox_simulation sim_launch.py

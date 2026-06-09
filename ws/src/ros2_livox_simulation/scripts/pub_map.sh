#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVOX_SIM_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$LIVOX_SIM_ROOT/install/setup.sh"

ros2 service call /localizer/relocalize interface/srv/Relocalize "
pcd_path: /accumulated_map_ds.pcd
x: 0.0
y: 0.0
z: 0.0
yaw: 0.0
roll: 0.0
pitch: 0.0
"

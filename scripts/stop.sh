#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="$ROOT_DIR"
ELEV_WS_DIR="${MAP_SIM_ELEV_WS_DIR:-/home/charles/NEXUS/tools/elevation_mapping_cupy_ros2_ws}"
WORLD_LIGHTING_CACHE_DIR="${TMPDIR:-/tmp}/map_sim_world_lighting"
GAZEBO_MASTER_PORT="${MAP_SIM_GAZEBO_MASTER_PORT:-11345}"

GRACE_SECONDS="${MAP_SIM_STOP_GRACE_SECONDS:-5}"
TERM_SECONDS="${MAP_SIM_STOP_TERM_SECONDS:-3}"
DRY_RUN=0
USER_ID="$(id -u)"

usage() {
  cat <<'EOF'
Usage: ./scripts/stop.sh [--dry-run] [--keep-rviz]

  --dry-run    Only print matching processes, do not send signals.
  --keep-rviz  Compatibility flag; rviz is no longer managed here.
EOF
}

log() {
  printf '[STOP] %s\n' "$*"
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

describe_tcp_listener() {
  local port="$1"
  local listener=""

  if command -v lsof >/dev/null 2>&1; then
    listener="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | tail -n +2 || true)"
    if [ -n "$listener" ]; then
      printf '%s\n' "$listener"
      return 0
    fi
  fi

  if command -v ss >/dev/null 2>&1; then
    listener="$(ss -lntp 2>/dev/null | awk -v port=":$port" '$1 == "LISTEN" && $4 ~ (port "$") { print }' || true)"
    if [ -n "$listener" ]; then
      printf '%s\n' "$listener"
    fi
  fi
}

warn_if_external_gazebo_master_owner() {
  local listener=""
  listener="$(describe_tcp_listener "$GAZEBO_MASTER_PORT")"
  if [ -z "$listener" ]; then
    return 0
  fi

  warn "Gazebo master port $GAZEBO_MASTER_PORT is still in use by a process outside this repo's scoped cleanup:"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    warn "$line"
  done <<< "$listener"
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --keep-rviz)
      :
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      warn "Unknown argument: $arg"
      usage
      exit 1
      ;;
  esac
done

SCOPED_PATTERNS=(
  # --- Launch wrappers (path-scoped) ---
  "$ROOT_DIR/scripts/run_sim.sh"
  "$ROOT_DIR/scripts/run_mppi.sh"
  "$ROOT_DIR/scripts/run_gp_fastlio.sh"
  "$ROOT_DIR/scripts/run_street_infer.sh"
  "$ROOT_DIR/scripts/run_elevation_mppi.sh"
  "$ROOT_DIR/scripts/run_lrae.sh"
  "$ROOT_DIR/install/ros2_livox_simulation/lib/ros2_livox_simulation/"
  "$WS_DIR/src/nexus_elevation_mppi/scripts/elevation_map_exporter.py"
  "$WS_DIR/src/nexus_elevation_mppi/scripts/traversability_to_map.py"
  "$WS_DIR/src/nexus_elevation_mppi/scripts/mppi_navigator.py"
  "$WS_DIR/src/nexus_elevation_mppi/scripts/novelty_explorer.py"
  "$WS_DIR/install/nexus_elevation_mppi/lib/nexus_elevation_mppi/"
  "$WS_DIR/install/nexus_sand_mpc/lib/nexus_sand_mpc/"
  "$WS_DIR/install/nexus_teleop/lib/nexus_teleop/pose_to_tf_bridge"
  "$WS_DIR/src/nexus_semantics/scripts/pointcept_semseg_node.py"
  "$WS_DIR/.external_worlds/"
  "$ELEV_WS_DIR/install/elevation_mapping_cupy/"
  "$ELEV_WS_DIR/src/elevation_mapping_cupy/"
  "$WORLD_LIGHTING_CACHE_DIR/"
  "$ROOT_DIR/open_depth_camera.sh"
  "python3 $WS_DIR/src/ros2_livox_simulation/scripts/runtime_depth_camera.py"
  "python3 $WS_DIR/src/ros2_livox_simulation/scripts/clound_acc.py"

  # --- ros2 launch / run commands ---
  "ros2 launch ros2_livox_simulation sim_launch.py"
  "ros2 launch ros2_livox_simulation sim_launch_omni.py"
  "ros2 launch elevation_mapping_cupy elevation_mapping.launch.py"
  "ros2 launch $ROOT_DIR/launch/lrae_exploration.py"
  "ros2 launch launch/lrae_exploration.py"
  "ros2 launch $ROOT_DIR/launch/nav2_mppi.launch.py"
  "ros2 run nexus_teleop pose_to_tf_bridge"
  "ros2 run nexus_gp_mapping gp_mapping_node"
  "ros2 run nexus_elevation_mppi novelty_explorer"
  "ros2 run nexus_elevation_mppi mppi_navigator"
  "ros2 run nexus_sand_mpc sand_mpc_compensator"

  # --- Gazebo (orphan-safe: match executable name directly) ---
  "gzserver"
  "gzclient"
  "ruby.*gz"
  "ign gazebo"

  # --- ROS nodes by executable name (orphan-safe) ---
  "elevation_mapping_node.py"
  "lrae_planner_node"
  "exploration_map_merge"
  "Traversibility_mapping"
  "localPlanner"
  "pathFollower"
  "gen_local_goal_node"
  "sim_truth_tf_publisher.py"
  "base_footprint_link_bridge.py"
  "map_odom_bridge.py"
  "robot_state_publisher"
  "rviz2"
  "spawn_entity.py"
  "clound_acc.py"
  "tf_pub"

  # --- Nav2 nodes ---
  "controller_server"
  "planner_server"
  "behavior_server"
  "smoother_server"
  "bt_navigator"
  "waypoint_follower"
  "lifecycle_manager"

  # --- FAST-LIO / Livox ---
  "fastlio2"
  "livox_ros_driver2"
)

is_pid_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

is_pid_zombie() {
  local pid="$1"
  local stat=""
  stat="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
  [ -n "$stat" ] && [[ "$stat" == Z* ]]
}

collect_process_tree_pids() {
  local root_pid="$1"
  if ! is_pid_running "$root_pid"; then
    return 0
  fi

  echo "$root_pid"

  local child_pid=""
  while read -r child_pid; do
    [ -n "$child_pid" ] || continue
    collect_process_tree_pids "$child_pid"
  done < <(ps -o pid= --ppid "$root_pid" 2>/dev/null || true)
}

collect_scoped_pattern_pids() {
  local pattern=""
  local root_pid=""
  for pattern in "${SCOPED_PATTERNS[@]}"; do
    while read -r root_pid; do
      [ -n "$root_pid" ] || continue
      collect_process_tree_pids "$root_pid"
    done < <(pgrep -u "$USER_ID" -f -- "$pattern" 2>/dev/null || true)
  done
}

collect_excluded_pids() {
  local pid="$$"
  while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
    echo "$pid"
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
  done
}

is_excluded_pid() {
  local candidate="$1"
  local excluded_pid=""
  for excluded_pid in "${EXCLUDED_PIDS[@]}"; do
    if [ "$candidate" = "$excluded_pid" ]; then
      return 0
    fi
  done
  return 1
}

collect_scoped_pattern_pids_excluding_current_tree() {
  local pattern=""
  local root_pid=""
  for pattern in "${SCOPED_PATTERNS[@]}"; do
    while read -r root_pid; do
      [ -n "$root_pid" ] || continue
      if is_excluded_pid "$root_pid"; then
        continue
      fi
      collect_process_tree_pids "$root_pid"
    done < <(pgrep -u "$USER_ID" -f -- "$pattern" 2>/dev/null || true)
  done
}

load_matching_pids() {
  readarray -t EXCLUDED_PIDS < <(collect_excluded_pids | awk 'NF && !seen[$0]++')
  readarray -t MATCHING_PIDS < <(
    {
      collect_scoped_pattern_pids_excluding_current_tree
    } | awk 'NF && !seen[$0]++'
  )

  local filtered_pids=()
  local pid=""
  for pid in "${MATCHING_PIDS[@]}"; do
    if is_excluded_pid "$pid"; then
      continue
    fi
    if is_pid_zombie "$pid"; then
      continue
    fi
    filtered_pids+=("$pid")
  done

  MATCHING_PIDS=("${filtered_pids[@]}")
}

print_matches() {
  if [ "${#MATCHING_PIDS[@]}" -eq 0 ]; then
    log "No matching simulation processes found."
    return 0
  fi

  log "Matched ${#MATCHING_PIDS[@]} process(es):"
  ps -fp "${MATCHING_PIDS[@]}"
}

wait_until_clear() {
  local timeout="$1"
  local deadline=$((SECONDS + timeout))

  while [ "$SECONDS" -lt "$deadline" ]; do
    load_matching_pids
    if [ "${#MATCHING_PIDS[@]}" -eq 0 ]; then
      return 0
    fi
    sleep 1
  done

  load_matching_pids
  [ "${#MATCHING_PIDS[@]}" -eq 0 ]
}

send_signal_to_matches() {
  local signal_name="$1"
  local wait_seconds="$2"

  load_matching_pids
  if [ "${#MATCHING_PIDS[@]}" -eq 0 ]; then
    return 0
  fi

  log "Sending SIG${signal_name} to ${#MATCHING_PIDS[@]} process(es)."
  if [ "$DRY_RUN" = "1" ]; then
    print_matches
    return 0
  fi

  kill "-${signal_name}" "${MATCHING_PIDS[@]}" 2>/dev/null || true
  wait_until_clear "$wait_seconds" || true
}

stop_ros2_daemon() {
  if ! command -v ros2 >/dev/null 2>&1; then
    return 0
  fi

  if [ "$DRY_RUN" = "1" ]; then
    log "Would run: ros2 daemon stop"
    return 0
  fi

  if command -v timeout >/dev/null 2>&1; then
    timeout 5s ros2 daemon stop >/dev/null 2>&1 || true
  else
    ros2 daemon stop >/dev/null 2>&1 || true
  fi
}

cleanup_pid_files() {
  rm -f "$ROOT_DIR/scripts/main_launch.pid" "$ROOT_DIR/scripts/runtime_depth_camera.pid" "$ROOT_DIR/scripts/rviz.pid"
}

log "Scanning for stale simulation processes..."
load_matching_pids
print_matches

if [ "${#MATCHING_PIDS[@]}" -eq 0 ]; then
  warn_if_external_gazebo_master_owner
  stop_ros2_daemon
  cleanup_pid_files
  exit 0
fi

send_signal_to_matches INT "$GRACE_SECONDS"
send_signal_to_matches TERM "$TERM_SECONDS"
send_signal_to_matches KILL 1
stop_ros2_daemon

load_matching_pids
if [ "${#MATCHING_PIDS[@]}" -gt 0 ]; then
  warn "Some processes are still alive after SIGKILL."
  ps -fp "${MATCHING_PIDS[@]}"
  exit 1
fi

warn_if_external_gazebo_master_owner

cleanup_pid_files
log "Cleanup finished. Simulation leftovers have been cleared."

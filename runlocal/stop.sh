#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="$ROOT_DIR/ws"
WORLD_LIGHTING_CACHE_DIR="${TMPDIR:-/tmp}/map_sim_world_lighting"

GRACE_SECONDS="${MAP_SIM_STOP_GRACE_SECONDS:-5}"
TERM_SECONDS="${MAP_SIM_STOP_TERM_SECONDS:-3}"
DRY_RUN=0
USER_ID="$(id -u)"

usage() {
  cat <<'EOF'
Usage: ./runlocal/stop.sh [--dry-run] [--keep-rviz]

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
  "$WS_DIR/install/ros2_livox_simulation/lib/ros2_livox_simulation/"
  "$WS_DIR/.external_worlds/"
  "$WORLD_LIGHTING_CACHE_DIR/"
  "$ROOT_DIR/open_depth_camera.sh"
  "python3 $WS_DIR/src/ros2_livox_simulation/scripts/runtime_depth_camera.py"
  "ros2 launch ros2_livox_simulation sim_launch.py"
  "ros2 launch ros2_livox_simulation sim_launch_omni.py"
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

load_matching_pids() {
  readarray -t EXCLUDED_PIDS < <(collect_excluded_pids | awk 'NF && !seen[$0]++')
  readarray -t MATCHING_PIDS < <(
    {
      collect_scoped_pattern_pids
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
    log "No matching Gazebo simulation processes found."
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
  rm -f "$ROOT_DIR/runlocal/main_launch.pid" "$ROOT_DIR/runlocal/runtime_depth_camera.pid" "$ROOT_DIR/runlocal/rviz.pid"
}

log "Scanning for stale Gazebo processes..."
load_matching_pids
print_matches

if [ "${#MATCHING_PIDS[@]}" -eq 0 ]; then
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

cleanup_pid_files
log "Cleanup finished. Gazebo leftovers have been cleared."

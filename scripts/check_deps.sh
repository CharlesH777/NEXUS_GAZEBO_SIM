#!/usr/bin/env bash
set -euo pipefail

check() {
  local path="$1"
  if [ -e "$path" ]; then
    echo "OK   $path"
  else
    echo "MISS $path"
  fi
}

echo "== Core files =="
check /opt/ros/humble/setup.bash
check /usr/local/lib/liblivox_lidar_sdk_shared.so
check /usr/local/include/livox_lidar_api.h

if [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  source /opt/ros/humble/setup.bash
  set -u
fi

echo
printf "%-45s %s\n" "COMMAND" "PATH"
for cmd in colcon rosdep gazebo gzserver gzclient xacro; do
  printf "%-45s " "$cmd"
  command -v "$cmd" || true
done

echo
cat <<'MSG'
If anything above shows MISS / empty path, install the missing dependency first.
MSG

#!/usr/bin/env bash
# LRAE 探索规划 - 集成到 NEXUS Livox MID-360 仿真

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
ROS_SETUP="/opt/ros/humble/setup.bash"
SIM_WS_SETUP="$ROOT_DIR/install/setup.bash"
PLANNER_WS_SETUP="$ROOT_DIR/install/setup.bash"
WORLD_NAME="${MAP_SIM_WORLD_NAME:-marsyard2020_map_only.world}"

apply_default_spawn_for_world() {
    local world="$1"

    export MAP_SIM_SPAWN_X="${MAP_SIM_SPAWN_X:-0.0}"
    export MAP_SIM_SPAWN_Y="${MAP_SIM_SPAWN_Y:-0.0}"

    case "$world" in
        marsyard2020_map_only.world)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-1.60}"
            ;;
        marsyard2021_map_only.world)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-2.90}"
            ;;
        marsyard2022_map_only.world)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-2.20}"
            ;;
        apollo15_map_only.world)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-0.85}"
            ;;
        rm_2026_slam_world.world)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-0.19}"
            ;;
        *)
            export MAP_SIM_SPAWN_Z="${MAP_SIM_SPAWN_Z:-0.5}"
            ;;
    esac
}

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

configure_render_env() {
    export MAP_SIM_GZCLIENT="${MAP_SIM_GZCLIENT:-1}"
    export MAP_SIM_ENABLE_RVIZ="${MAP_SIM_ENABLE_RVIZ:-1}"
    export MAP_SIM_ENABLE_HEADLESS_RENDERING="${MAP_SIM_ENABLE_HEADLESS_RENDERING:-0}"

    if [ "${MAP_SIM_GZCLIENT}" = "1" ]; then
        unset QT_QPA_PLATFORM || true
        unset QT_X11_NO_MITSHM || true
        unset LIBGL_ALWAYS_SOFTWARE || true

        if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
            echo "[WARN] MAP_SIM_GZCLIENT=1 but no DISPLAY/WAYLAND_DISPLAY is set."
            echo "[WARN] Gazebo UI / RViz may not open. To force headless mode use:"
            echo "[WARN]   MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash ./scripts/run_lrae.sh"
        fi
    else
        unset DISPLAY || true
        unset WAYLAND_DISPLAY || true
        export QT_QPA_PLATFORM=offscreen
        export QT_X11_NO_MITSHM=1
        export LIBGL_ALWAYS_SOFTWARE=1
    fi
}

wait_for_topic_once() {
    local topic="$1"
    local timeout_sec="${2:-120}"
    local deadline=$((SECONDS + timeout_sec))

    while [ "$SECONDS" -lt "$deadline" ]; do
        if ros2 topic list >/dev/null 2>&1 && ros2 topic list | grep -Fxq "$topic"; then
            if timeout 5 ros2 topic echo --once "$topic" >/dev/null 2>&1; then
                return 0
            fi
        fi
        sleep 1
    done

    return 1
}

cleanup_lrae_processes() {
    local patterns=(
        "ros2 launch $ROOT_DIR/launch/lrae_exploration.py"
        "ros2 launch launch/lrae_exploration.py"
        "/install/sensor_conversion/lib/sensor_conversion/slam_sim_output_node"
        "/install/fitplane/lib/fitplane/Traversibility_mapping"
        "/install/lrae_planner/lib/lrae_planner/exploration_map_merge"
        "/install/lrae_planner/lib/lrae_planner/lrae_planner_node"
        "/install/local_planner/lib/local_planner/localPlanner"
        "/install/local_planner/lib/local_planner/pathFollower"
        "/install/gen_local_goal/lib/gen_local_goal/gen_local_goal_node"
        "/install/sensor_conversion/lib/sensor_conversion/sim_truth_tf_publisher.py"
        "/opt/ros/humble/lib/tf2_ros/static_transform_publisher --x 0 --y 0 --z 0 --roll 0 --pitch 0 --yaw 0 --frame-id world --child-frame-id map --ros-args"
        "/opt/ros/humble/lib/tf2_ros/static_transform_publisher --x 0 --y 0 --z -0.3 --roll 0 --pitch 0 --yaw 0 --frame-id sensor --child-frame-id base_link --ros-args"
    )

    local pattern=""
    for pattern in "${patterns[@]}"; do
        pkill -u "$(id -u)" -f -- "$pattern" >/dev/null 2>&1 || true
    done
}

cleanup_background_jobs() {
    local pid=""
    for pid in "${LRAE_PID:-}" "${LIVOX_PID:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1 || true
            wait "$pid" >/dev/null 2>&1 || true
        fi
    done
}

echo "═══════════════════════════════════════════════════"
echo "  NEXUS + LRAE 探索规划器"
echo "  Livox MID-360 仿真环境"
echo "═══════════════════════════════════════════════════"
echo ""

# 检查构建
if [ ! -f "$ROS_SETUP" ]; then
    echo "❌ 错误：缺少 ROS 2 Humble 环境: $ROS_SETUP"
    exit 1
fi

if [ ! -f "$SIM_WS_SETUP" ]; then
    echo "❌ 错误：缺少仿真工作区环境: $SIM_WS_SETUP"
    echo "   请先运行: ./scripts/build.sh"
    exit 1
fi

if [ ! -f "$PLANNER_WS_SETUP" ]; then
    echo "❌ 错误：缺少 LRAE 规划工作区环境: $PLANNER_WS_SETUP"
    echo "   请先在仓库根目录执行 colcon build"
    exit 1
fi

# Source 环境
sanitize_python_env
configure_render_env
apply_default_spawn_for_world "$WORLD_NAME"
set +u
source "$ROS_SETUP"
source "$SIM_WS_SETUP"
source "$PLANNER_WS_SETUP"
set -u

if [ "${MAP_SIM_FORCE_CLEAN_START:-1}" = "1" ] && [ -x "$ROOT_DIR/scripts/stop.sh" ]; then
    echo "[INFO] Clean start: stopping stale Gazebo / ROS simulation processes"
    "$ROOT_DIR/scripts/stop.sh" --keep-rviz || true
    cleanup_lrae_processes
fi

echo "[INFO] 启动 NEXUS Livox 仿真 + LRAE 探索..."
echo "[INFO] world=${WORLD_NAME} spawn=(${MAP_SIM_SPAWN_X}, ${MAP_SIM_SPAWN_Y}, ${MAP_SIM_SPAWN_Z})"
echo "[INFO] gazebo_ui=${MAP_SIM_GZCLIENT} rviz=${MAP_SIM_ENABLE_RVIZ} headless_rendering=${MAP_SIM_ENABLE_HEADLESS_RENDERING}"
echo ""

trap cleanup_background_jobs EXIT INT TERM

# 启动 Livox 仿真
ros2 launch ros2_livox_simulation sim_launch_omni.py \
    world_name:="${WORLD_NAME}" \
    use_gui:="${MAP_SIM_GZCLIENT}" \
    enable_headless_rendering:="${MAP_SIM_ENABLE_HEADLESS_RENDERING}" \
    enable_livox:=1 \
    enable_rviz:="${MAP_SIM_ENABLE_RVIZ}" \
    enable_tf_pub:=1 \
    enable_pointcloud_pipeline:=1 \
    pointcloud_publish_world:=1 \
    spawn_x:="${MAP_SIM_SPAWN_X}" \
    spawn_y:="${MAP_SIM_SPAWN_Y}" \
    spawn_z:="${MAP_SIM_SPAWN_Z}" &

LIVOX_PID=$!
echo "[INFO] Livox 仿真启动 (PID: $LIVOX_PID)"

# 等待仿真启动
echo "[INFO] 等待仿真机器人就绪 (/nav_odom)..."
if ! wait_for_topic_once "/nav_odom" 180; then
    echo "[ERR] 仿真未能在 180s 内发布 /nav_odom，取消启动 LRAE。"
    exit 1
fi

# 启动 LRAE 探索节点
echo "[INFO] 启动 LRAE 探索规划..."
ros2 launch "$ROOT_DIR/launch/lrae_exploration.py" &

LRAE_PID=$!
echo "[INFO] LRAE 探索启动 (PID: $LRAE_PID)"

echo ""
echo "✅ 系统已启动！"
echo ""
echo "监控命令："
echo "  ros2 topic hz /cloud_registered      # Livox 点云"
echo "  ros2 topic hz /plane_OccMap          # 通行性地图"
echo "  ros2 topic hz /cmd_vel               # 速度指令"
echo "  ros2 node list                       # 所有节点"
echo ""
echo "按 Ctrl+C 停止..."

# 等待，任一关键进程退出都视为失败并清理另一个
wait -n "$LIVOX_PID" "$LRAE_PID"
status=$?

if ! kill -0 "$LIVOX_PID" >/dev/null 2>&1; then
    echo "[ERR] Livox/Gazebo 仿真进程已退出，LRAE 已失去上游数据。"
fi

if ! kill -0 "$LRAE_PID" >/dev/null 2>&1; then
    echo "[ERR] LRAE 规划进程已退出。"
fi

exit "$status"

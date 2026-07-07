#!/usr/bin/env bash
# scripts/build_check.sh
#
# NEXUS_GAZEBO_SIM 一站式构建脚本：环境依赖检测 → 自动编译 → 构建后校验。
#
# 本次脚本针对以下已知坑点做了自动处理：
#   1. conda python3.13 与 ROS humble(python3.10) 冲突 → 清掉 conda 环境，强制 /usr/bin/python3
#   2. grid_map_msgs 不在系统 apt 里，由 elevation_mapping_cupy_ros2_ws 提供 → 自动发现并 source
#   3. build.sh 里 rosdep 未初始化被跳过 → 不依赖 rosdep，改做显式包存在性检测
#   4. livox_ros_driver2 必须先于 ros2_livox_simulation 构建 → 用 colcon 包依赖自动排序
#   5. 构建后只看 "Finished" 不够 → 增加 ros2 pkg / executables / ldd / py_compile / import 全链路校验
#
# 用法：
#   bash scripts/build_check.sh                    # 检测+编译主线 7 包+校验
#   bash scripts/build_check.sh --with-third-party # 额外编译 src/third_party（可选栈）
#   bash scripts/build_check.sh --install          # 尝试 sudo apt 自动安装缺失 apt 依赖
#   bash scripts/build_check.sh --packages <a,b>   # 只构建指定包
#   bash scripts/build_check.sh --check-only       # 跳过编译，只做构建后校验
#   bash scripts/build_check.sh --help
#
# 退出码：
#   0  全部通过
#   1  环境依赖缺失（致命）
#   2  编译失败
#   3  构建后校验失败

set -euo pipefail

# ---------------------------------------------------------------------------
# 路径与可配置项
# ---------------------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS_DIR="$ROOT_DIR"
ELEV_WS_DIR="${MAP_SIM_ELEV_WS_DIR:-$HOME/NEXUS/tools/elevation_mapping_cupy_ros2_ws}"
ROS_SETUP="/opt/ros/humble/setup.bash"

# 主线包（始终构建，按 colcon 依赖自动排序）
MAIN_PACKAGES=(
  livox_ros_driver2
  ros2_livox_simulation
  nexus_elevation_mppi
  nexus_fastlio
  nexus_gp_mapping
  nexus_sand_mpc
  nexus_teleop
)

# 第三方可选包（--with-third-party 时构建）
THIRD_PARTY_PACKAGES=(
  minkindr kdtree planner_msgs planner_semantic_msgs planner_common
  voxblox voxblox_msgs adaptive_obb_ros fitplane gen_local_goal
  local_planner lrae_planner sensor_conversion gbplanner
  m_explore_ros2 explore_lite_msgs multirobot_map_merge
)

# 构建后必须能被 ros2 发现的包
REQUIRED_BUILT_PACKAGES=("${MAIN_PACKAGES[@]}")

# 编译期需要、由外部 workspace 提供的 ROS 包（非本工作区）
EXTERNAL_ROS_DEPS=(grid_map_msgs grid_map_core grid_map_cv grid_map_ros)

# 编译期需要的系统 ROS 包（apt 提供）
SYSTEM_ROS_DEPS=(
  pcl_ros pcl_conversions tf2_geometry_msgs tf2_sensor_msgs tf2_ros
  visualization_msgs message_filters map_msgs nav_msgs std_srvs action_msgs
  rosgraph_msgs rosidl_default_generators ament_cmake_gtest rclcpp_components
)

# 退出码
RC_OK=0
RC_ENV=1
RC_BUILD=2
RC_CHECK=3

# 计数
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# 命令行参数
WITH_THIRD_PARTY=0
TRY_INSTALL=0
CHECK_ONLY=0
SELECT_PACKAGES=""

# ---------------------------------------------------------------------------
# 颜色输出
# ---------------------------------------------------------------------------
if [ -t 1 ] && command -v tput >/dev/null 2>&1; then
  C_RED=$(tput setaf 1); C_GREEN=$(tput setaf 2); C_YELLOW=$(tput setaf 3)
  C_BLUE=$(tput setaf 4); C_BOLD=$(tput bold); C_RESET=$(tput sgr0)
else
  C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
fi

log_info()  { printf -- "${C_BLUE}[INFO]${C_RESET}  %s\n" "$*"; }
log_ok()    { printf -- "${C_GREEN}[OK]${C_RESET}    %s\n" "$*"; PASS_COUNT=$((PASS_COUNT+1)); }
log_warn()  { printf -- "${C_YELLOW}[WARN]${C_RESET}  %s\n" "$*"; WARN_COUNT=$((WARN_COUNT+1)); }
log_fail()  { printf -- "${C_RED}[FAIL]${C_RESET}  %s\n" "$*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
log_stage() { printf -- "\n${C_BOLD}${C_BLUE}=== %s ===${C_RESET}\n" "$*"; }
log_step()  { printf -- "${C_BOLD}--- %s ---${C_RESET}\n" "$*"; }

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
NEXUS_GAZEBO_SIM 构建 + 校验脚本

用法: bash scripts/build_check.sh [选项]

选项:
  --with-third-party   额外编译 src/third_party 下的可选包(LRAE/GP/voxblox 等)
  --install            尝试 sudo apt-get 自动安装缺失的 apt 依赖(需要密码)
  --packages <a,b,c>   只构建指定包(逗号分隔)，跳过默认主线包
  --check-only         跳过编译，只做构建后校验
  --help, -h           显示帮助

环境变量:
  MAP_SIM_ELEV_WS_DIR  elevation_mapping_cupy_ros2_ws 路径
                       (默认: ~/NEXUS/tools/elevation_mapping_cupy_ros2_ws)
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --with-third-party) WITH_THIRD_PARTY=1; shift;;
    --install)          TRY_INSTALL=1; shift;;
    --check-only)       CHECK_ONLY=1; shift;;
    --packages)         SELECT_PACKAGES="$2"; shift 2;;
    --help|-h)          usage; exit 0;;
    *) log_fail "未知参数: $1"; usage; exit $RC_ENV;;
  esac
done

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

# 清掉 conda / 虚拟环境，强制使用系统 python3.10，避免 rclpy pybind11 版本不匹配
sanitize_python_env() {
  unset PYTHONHOME PYTHONPATH CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER \
        CONDA_SHLVL CONDA_EXE CONDA_PYTHON_EXE _CE_CONDA _CE_M || true
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

# 检查文件/目录/命令是否存在，统一打印
check_path() {
  local desc="$1" path="$2"
  if [ -e "$path" ]; then
    log_ok "$desc: $path"
    return 0
  else
    log_fail "$desc: $path (缺失)"
    return 1
  fi
}

check_cmd() {
  local desc="$1" cmd="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    log_ok "$desc: $(command -v "$cmd")"
    return 0
  else
    log_fail "$desc: 未找到 $cmd"
    return 1
  fi
}

# 用 pkg-config 检查系统库
check_pkgconfig() {
  local lib="$1"
  if pkg-config --exists "$lib" 2>/dev/null; then
    log_ok "系统库 $lib (pkg-config)"
    return 0
  else
    log_fail "系统库 $lib (pkg-config 找不到)"
    return 1
  fi
}

# 用 dpkg 检查 apt 包
check_dpkg() {
  local lib="$1" pkg="$2"
  if dpkg -l "$pkg" 2>/dev/null | grep -q '^ii'; then
    log_ok "系统库 $lib ($pkg)"
    return 0
  else
    log_fail "系统库 $lib ($pkg 未安装)"
    return 1
  fi
}

# 收集缺失的 apt 包，便于一次性安装
declare -a MISSING_APT=()
record_missing_apt() {
  MISSING_APT+=("$1")
}

# ---------------------------------------------------------------------------
# Phase 1: 环境依赖检测
# ---------------------------------------------------------------------------
phase_env_check() {
  log_stage "Phase 1: 环境依赖检测"

  log_step "1.1 核心 ROS / SDK 文件"
  local core_ok=1
  check_path "ROS Humble setup"   "$ROS_SETUP"         || core_ok=0
  check_path "Livox SDK2 .so"     "/usr/local/lib/liblivox_lidar_sdk_shared.so" || core_ok=0
  check_path "Livox SDK2 header"  "/usr/local/include/livox_lidar_api.h"        || core_ok=0
  if [ $core_ok -eq 0 ]; then
    log_fail "核心文件缺失，无法继续。请先运行 scripts/install_deps.sh 并安装 Livox-SDK2。"
    return $RC_ENV
  fi

  log_step "1.2 命令行工具"
  sanitize_python_env
  # 先 source ROS 以便 ros2/colcon 可用
  if [ -f "$ROS_SETUP" ]; then
    set +u; source "$ROS_SETUP"; set -u
  fi
  local cmd_ok=1
  check_cmd "colcon"  "colcon"  || cmd_ok=0
  check_cmd "rosdep"  "rosdep"  || { cmd_ok=0; log_warn "rosdep 缺失，将跳过 rosdep 自动安装(脚本不依赖它)"; }
  check_cmd "gazebo"  "gazebo"  || cmd_ok=0
  check_cmd "gzserver" "gzserver" || cmd_ok=0
  check_cmd "xacro"   "xacro"   || cmd_ok=0
  check_cmd "cmake"   "cmake"   || cmd_ok=0
  check_cmd "pkg-config" "pkg-config" || cmd_ok=0
  if [ $cmd_ok -eq 0 ]; then
    log_fail "必要命令行工具缺失"
    return $RC_ENV
  fi

  log_step "1.3 Python 解释器(必须 3.10，与 ROS humble rclpy 匹配)"
  if [ -x /usr/bin/python3 ]; then
    local pyver
    pyver=$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [ "$pyver" = "3.10" ]; then
      log_ok "/usr/bin/python3 版本 $pyver"
    else
      log_fail "/usr/bin/python3 版本 $pyver，需要 3.10"
      return $RC_ENV
    fi
  else
    log_fail "/usr/bin/python3 不存在"
    return $RC_ENV
  fi
  # 检测当前 shell 是否被 conda 污染
  if [ -n "${CONDA_DEFAULT_ENV:-}" ] || [[ "$(command -v python3)" == *conda* ]]; then
    log_warn "检测到 conda 环境，构建期间将被 sanitize_python_env 清除"
  fi

  log_step "1.4 系统库(pkg-config / dpkg)"
  local lib_ok=1
  check_pkgconfig "eigen3"     || lib_ok=0
  check_pkgconfig "pcl_common-1.12" 2>/dev/null || check_dpkg "PCL" "libpcl-dev" || lib_ok=0
  check_pkgconfig "protobuf"   || lib_ok=0
  check_pkgconfig "flann"      2>/dev/null || check_dpkg "FLANN" "libflann-dev" || lib_ok=0
  check_dpkg    "gflags" "libgflags-dev"       || { lib_ok=0; record_missing_apt "libgflags-dev"; }
  check_dpkg    "glog"   "libgoogle-glog-dev"  || { lib_ok=0; record_missing_apt "libgoogle-glog-dev"; }
  check_dpkg    "Qt5"    "qtbase5-dev"         || { lib_ok=0; record_missing_apt "qtbase5-dev"; }
  check_dpkg    "Boost"  "libboost-all-dev"    2>/dev/null || check_pkgconfig "boost" || { lib_ok=0; record_missing_apt "libboost-all-dev"; }
  check_dpkg    "Eigen3" "libeigen3-dev"       2>/dev/null || true  # pkg-config 已查
  if [ $lib_ok -eq 0 ]; then
    log_warn "部分系统库缺失(仅影响第三方可选栈；主线 7 包不一定需要)"
  fi

  log_step "1.5 elevation_mapping_cupy workspace(提供 grid_map_msgs)"
  local elev_ok=0
  if [ -f "$ELEV_WS_DIR/install/setup.bash" ]; then
    log_ok "elevation workspace: $ELEV_WS_DIR"
    elev_ok=1
  else
    # 尝试项目内 tools/elevation_ros2
    if [ -f "$ROOT_DIR/tools/elevation_ros2/install/setup.bash" ]; then
      ELEV_WS_DIR="$ROOT_DIR/tools/elevation_ros2"
      log_ok "elevation workspace(项目内): $ELEV_WS_DIR"
      elev_ok=1
    else
      log_warn "未找到 elevation_mapping_cupy_ros2_ws"
      log_warn "  查找路径1: $ELEV_WS_DIR"
      log_warn "  查找路径2: $ROOT_DIR/tools/elevation_ros2"
      log_warn "  可通过 MAP_SIM_ELEV_WS_DIR 环境变量指定"
      log_warn "  缺失时 nexus_elevation_mppi 将无法编译(grid_map_msgs)"
    fi
  fi

  log_step "1.6 ROS 包存在性(source 后检测)"
  if [ $elev_ok -eq 1 ]; then
    set +u; source "$ELEV_WS_DIR/install/setup.bash"; set -u
  fi

  local ros_missing=0
  # 外部 workspace 提供的
  for p in "${EXTERNAL_ROS_DEPS[@]}"; do
    if ros2 pkg list 2>/dev/null | grep -qx "$p"; then
      log_ok "ROS 包 $p (elevation ws)"
    else
      log_fail "ROS 包 $p 缺失(elevation workspace 未提供)"
      ros_missing=1
    fi
  done
  # apt 提供的
  for p in "${SYSTEM_ROS_DEPS[@]}"; do
    if ros2 pkg list 2>/dev/null | grep -qx "$p"; then
      log_ok "ROS 包 $p (apt)"
    else
      log_fail "ROS 包 $p 缺失"
      record_missing_apt "ros-humble-$(echo "$p" | tr '_' '-')"
      ros_missing=1
    fi
  done

  # 尝试自动安装
  if [ ${#MISSING_APT[@]} -gt 0 ]; then
    if [ $TRY_INSTALL -eq 1 ]; then
      log_step "1.7 尝试 sudo apt 安装缺失依赖"
      local apt_list
      apt_list=$(printf '%s\n' "${MISSING_APT[@]}" | sort -u | tr '\n' ' ')
      log_info "apt install: $apt_list"
      sudo apt-get update && sudo apt-get install -y $apt_list
      # 重新 source 并复检
      set +u; source "$ROS_SETUP"; [ $elev_ok -eq 1 ] && source "$ELEV_WS_DIR/install/setup.bash"; set -u
      ros_missing=0
      for p in "${SYSTEM_ROS_DEPS[@]}"; do
        ros2 pkg list 2>/dev/null | grep -qx "$p" || { log_fail "重检仍缺: $p"; ros_missing=1; }
      done
    else
      log_warn "检测到缺失 apt 依赖，可用 --install 自动安装，或手动执行:"
      local apt_list
      apt_list=$(printf '%s\n' "${MISSING_APT[@]}" | sort -u | tr '\n' ' ')
      log_warn "  sudo apt-get install -y $apt_list"
    fi
  fi

  # grid_map_msgs 是主线硬依赖
  if ! ros2 pkg list 2>/dev/null | grep -qx "grid_map_msgs"; then
    log_fail "grid_map_msgs 不可用 → nexus_elevation_mppi 无法编译"
    log_info "修复方案: 构建 ~/NEXUS/tools/elevation_mapping_cupy_ros2_ws，或:"
    log_info "  sudo apt-get install -y ros-humble-grid-map-msgs"
    return $RC_ENV
  fi

  if [ $ros_missing -eq 1 ] && [ $TRY_INSTALL -eq 0 ]; then
    log_warn "部分 ROS 包缺失，可能导致第三方栈或部分功能不可用；主线构建会继续尝试"
  fi

  log_ok "Phase 1 环境检测完成"
  return 0
}

# ---------------------------------------------------------------------------
# Phase 2: 编译
# ---------------------------------------------------------------------------
phase_build() {
  log_stage "Phase 2: 编译"

  if [ $CHECK_ONLY -eq 1 ]; then
    log_info "跳过编译(--check-only)"
    return 0
  fi

  sanitize_python_env
  set +u
  source "$ROS_SETUP"
  [ -f "$ELEV_WS_DIR/install/setup.bash" ] && source "$ELEV_WS_DIR/install/setup.bash"
  # 增量构建时 source 已有 install
  [ -f "$WS_DIR/install/setup.bash" ] && source "$WS_DIR/install/setup.bash"
  set -u

  # 确定要构建的包列表
  local pkgs=()
  if [ -n "$SELECT_PACKAGES" ]; then
    IFS=',' read -ra pkgs <<< "$SELECT_PACKAGES"
  else
    pkgs=("${MAIN_PACKAGES[@]}")
    if [ $WITH_THIRD_PARTY -eq 1 ]; then
      pkgs+=("${THIRD_PARTY_PACKAGES[@]}")
    fi
  fi

  log_step "2.1 待构建包(${#pkgs[@]} 个)"
  printf '  %s\n' "${pkgs[@]}"

  log_step "2.2 colcon build"
  # 用 --packages-select 逐个检测存在性，避免 colcon 因不存在的包名报错
  local valid_pkgs=()
  local all_src_pkgs
  all_src_pkgs=$(colcon list --names-only 2>/dev/null || true)
  for p in "${pkgs[@]}"; do
    if echo "$all_src_pkgs" | grep -qx "$p"; then
      valid_pkgs+=("$p")
    else
      log_warn "包 $p 在 src/ 下不存在，跳过"
    fi
  done

  if [ ${#valid_pkgs[@]} -eq 0 ]; then
    log_fail "没有有效的包可构建"
    return $RC_BUILD
  fi

  local cmake_args=(-DROS_EDITION=ROS2 -DHUMBLE_ROS=humble)
  local build_log
  build_log="$WS_DIR/build_check_$(date +%Y%m%d_%H%M%S).log"
  log_info "构建日志: $build_log"

  if colcon build --packages-select "${valid_pkgs[@]}" \
        --cmake-args "${cmake_args[@]}" 2>&1 | tee "$build_log"; then
    log_ok "colcon build 成功"
  else
    log_fail "colcon build 失败(见 $build_log)"
    # 提取失败包
    grep -E 'Failed <<<' "$build_log" || true
    return $RC_BUILD
  fi

  log_ok "Phase 2 编译完成"
  return 0
}

# ---------------------------------------------------------------------------
# Phase 3: 构建后校验
# ---------------------------------------------------------------------------
phase_check() {
  log_stage "Phase 3: 构建后校验"

  sanitize_python_env
  set +u
  source "$ROS_SETUP"
  [ -f "$ELEV_WS_DIR/install/setup.bash" ] && source "$ELEV_WS_DIR/install/setup.bash"
  [ -f "$WS_DIR/install/setup.bash" ] && source "$WS_DIR/install/setup.bash"
  set -u

  local check_failed=0

  log_step "3.1 install/setup.bash"
  if [ -f "$WS_DIR/install/setup.bash" ]; then
    log_ok "install/setup.bash 存在"
  else
    log_fail "install/setup.bash 不存在(构建未产物化)"
    return $RC_CHECK
  fi

  log_step "3.2 主线包 ros2 发现性"
  for p in "${REQUIRED_BUILT_PACKAGES[@]}"; do
    if ros2 pkg list 2>/dev/null | grep -qx "$p"; then
      log_ok "ros2 发现 $p"
    else
      log_fail "ros2 未发现 $p"
      check_failed=1
    fi
  done

  log_step "3.3 入口点(executables)"
  local expected_exec=(
    "nexus_elevation_mppi:mppi_navigator"
    "nexus_elevation_mppi:novelty_explorer"
    "nexus_elevation_mppi:traversability_to_map"
    "nexus_elevation_mppi:elevation_map_exporter"
    "nexus_sand_mpc:sand_mpc_compensator"
    "nexus_fastlio:fastlio_imu_adapter"
    "nexus_fastlio:fastlio_lidar_adapter"
    "nexus_gp_mapping:gp_mapping_node"
    "nexus_teleop:pose_to_tf_bridge"
    "livox_ros_driver2:livox_ros_driver2_node"
    "ros2_livox_simulation:cmd_vel_to_swerve"
    "ros2_livox_simulation:spawn_omni_controllers"
  )
  for entry in "${expected_exec[@]}"; do
    local pkg="${entry%%:*}" exe="${entry##*:}"
    if ros2 pkg executables "$pkg" 2>/dev/null | grep -qw "$exe"; then
      log_ok "executable $pkg/$exe"
    else
      log_fail "executable $pkg/$exe 缺失"
      check_failed=1
    fi
  done

  log_step "3.4 C++ 二进制动态库依赖(ldd)"
  local mppi_bin="$WS_DIR/install/nexus_elevation_mppi/lib/nexus_elevation_mppi/mppi_navigator"
  if [ -x "$mppi_bin" ]; then
    local miss
    miss=$(ldd "$mppi_bin" 2>&1 | grep -c 'not found' || true)
    if [ "$miss" -eq 0 ]; then
      log_ok "mppi_navigator ldd 无缺失"
    else
      log_fail "mppi_navigator ldd 缺失 $miss 项:"
      ldd "$mppi_bin" 2>&1 | grep 'not found' | sed 's/^/      /'
      check_failed=1
    fi
  else
    log_fail "mppi_navigator 二进制不存在: $mppi_bin"
    check_failed=1
  fi

  # ros2_livox_simulation 的 .so
  local so_miss_total=0
  while IFS= read -r so; do
    local m
    m=$(ldd "$so" 2>&1 | grep -c 'not found' || true)
    if [ "$m" -ne 0 ]; then
      log_fail "$(basename "$so") ldd 缺失 $m 项"
      ldd "$so" 2>&1 | grep 'not found' | sed 's/^/      /'
      so_miss_total=$((so_miss_total+m))
      check_failed=1
    fi
  done < <(find "$WS_DIR/install/ros2_livox_simulation" -name '*.so' 2>/dev/null)
  if [ $so_miss_total -eq 0 ] && [ -d "$WS_DIR/install/ros2_livox_simulation" ]; then
    log_ok "ros2_livox_simulation 所有 .so ldd 无缺失"
  fi

  log_step "3.5 Python 脚本语法(py_compile)"
  local py_scripts=(
    "src/nexus_elevation_mppi/scripts/novelty_explorer.py"
    "src/nexus_elevation_mppi/scripts/traversability_to_map.py"
    "src/nexus_elevation_mppi/scripts/elevation_map_exporter.py"
  )
  for s in "${py_scripts[@]}"; do
    if /usr/bin/python3 -m py_compile "$WS_DIR/$s" 2>/dev/null; then
      log_ok "py_compile $(basename "$s")"
    else
      log_fail "py_compile $(basename "$s") 失败"
      /usr/bin/python3 -m py_compile "$WS_DIR/$s" 2>&1 | sed 's/^/      /'
      check_failed=1
    fi
  done

  log_step "3.6 Python 节点导入(/usr/bin/python3)"
  local import_test
  import_test=$(/usr/bin/python3 - <<'PY' 2>&1 || true
import sys
sys.path.insert(0, "install/nexus_sand_mpc/lib/python3.10/site-packages")
import rclpy
import numpy
from nexus_sand_mpc.sand_mpc_controller import SandMpcControllerMIMO
print("OK rclpy/numpy/SandMpcControllerMIMO")
PY
)
  if echo "$import_test" | grep -q "OK rclpy"; then
    log_ok "Python 导入: $import_test"
  else
    log_fail "Python 导入失败:"
    echo "$import_test" | sed 's/^/      /'
    check_failed=1
  fi

  log_step "3.7 launch 文件解析"
  if ros2 launch --print "$WS_DIR/launch/nav2_mppi.launch.py" >/dev/null 2>&1; then
    log_ok "launch/nav2_mppi.launch.py 解析通过"
  else
    log_fail "launch/nav2_mppi.launch.py 解析失败"
    check_failed=1
  fi

  if [ $check_failed -eq 1 ]; then
    log_fail "Phase 3 校验存在失败项"
    return $RC_CHECK
  fi

  log_ok "Phase 3 校验全部通过"
  return 0
}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
main() {
  bash "$ROOT_DIR/project_identity/logo/play_logo_intro.sh" 30 golden || true
  printf -- "${C_BOLD}NEXUS_GAZEBO_SIM 构建 + 校验${C_RESET}\n"
  log_info "工作区: $WS_DIR"
  log_info "elevation ws: $ELEV_WS_DIR"
  log_info "Python: /usr/bin/python3 (强制 3.10)"

  phase_env_check || { log_stage "中断: 环境检测未通过"; print_summary; exit $RC_ENV; }
  phase_build     || { log_stage "中断: 编译失败"; print_summary; exit $RC_BUILD; }
  phase_check     || { log_stage "中断: 校验失败"; print_summary; exit $RC_CHECK; }

  print_summary
  exit $RC_OK
}

print_summary() {
  log_stage "汇总"
  printf "  通过: ${C_GREEN}%d${C_RESET}  警告: ${C_YELLOW}%d${C_RESET}  失败: ${C_RED}%d${C_RESET}\n" \
    "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
  if [ "$FAIL_COUNT" -eq 0 ]; then
    printf -- "\n${C_GREEN}${C_BOLD}✓ 全部通过。下一步:${C_RESET}\n"
    printf "  bash scripts/run_mppi.sh            # 完整自动探索\n"
    printf "  MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh  # headless\n"
  else
    printf -- "\n${C_RED}${C_BOLD}✗ 有 %d 项失败，请按上方日志排查。${C_RESET}\n" "$FAIL_COUNT"
  fi
}

main "$@"

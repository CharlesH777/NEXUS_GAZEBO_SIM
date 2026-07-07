# NEXUS_GAZEBO_SIM — scripts/ 目录详解

> 本文档对 `scripts/` 目录下的所有脚本逐一拆解：职责、调用关系、环境变量、
> 依赖、内部函数、错误处理、典型用法。目标是看完这一份就能定位任意脚本的
> 任意行为，不需要再翻源码。

---

## 目录

1. [架构总览](#1-架构总览)
2. [调用图](#2-调用图)
3. [入口层 — 用户直接调用的脚本](#3-入口层--用户直接调用的脚本)
4. [核心启动层 — run_sim.sh 深度解析](#4-核心启动层--run_simsh-深度解析)
5. [导航堆栈层 — run_mppi.sh / run_elevation_mppi.sh](#5-导航堆栈层)
6. [GP 建图层 — run_gp_fastlio.sh / run_gp_nav.sh](#6-gp-建图层)
7. [LRAE 探索层 — run_lrae.sh / monitor_lrae.sh](#7-lrae-探索层)
8. [已移除能力 — street_infer](#8-已移除能力--street_infer)
9. [构建层 — build.sh / build_fastlio.sh](#9-构建层)
10. [工具层 — stop.sh / open_depth_camera.sh / open_teleop.sh / 便捷入口](#10-工具层)
11. [Python 节点](#11-python-节点)
12. [utils/ 子目录](#12-utils-子目录)
13. [环境变量完整索引](#13-环境变量完整索引)
14. [进程清理机制](#14-进程清理机制)
15. [已知限制与注意事项](#15-已知限制与注意事项)

---

## 1. 架构总览

```
scripts/
├── start.sh                     # 顶层入口 → 设默认开关 → exec run_sim.sh
├── run_sim.sh                   # 核心仿真启动（Gazebo + Livox + RViz + 点云管线）
├── run_mppi.sh                  # 全链路探索堆栈（Gazebo + 高程图 + MPPI + sand MPC + 探索）
├── run_elevation_mppi.sh        # CuPy 高程图 + MPPI 导航（不含 sand MPC / 探索）
├── run_gp_fastlio.sh            # FAST-LIO2 + GP 建图
├── run_gp_nav.sh                # GP 建图（无 FAST-LIO）
├── run_fastlio.sh               # FAST-LIO2 便捷启动 → run_sim.sh
├── run_lrae.sh                  # LRAE 探索规划器
├── monitor_lrae.sh              # LRAE 长时间监控（不启动进程）
│
├── stop.sh                      # 进程清理（Gazebo / ROS / Nav2 / FAST-LIO 全覆盖）
├── open_depth_camera.sh         # 运行时深度相机挂载
├── open_teleop.sh               # 手柄 / 键盘遥控 GUI
│
├── run_sim_gui.sh               # 便捷入口：强制 GUI + RViz
├── run_sim_omni.sh              # 便捷入口：显式 omni 变体
├── run_sim_camera.sh            # 便捷入口：强制深度相机
│
├── build.sh                     # 工作区构建（livox_ros_driver2 + ros2_livox_simulation）
├── build_fastlio.sh             # FAST-LIO2 单独构建
├── check_deps.sh                # 依赖检查
├── install_deps.sh              # apt 依赖安装
│
├── continuous_navigator.py      # 连续导航节点（planner+controller 直连）
├── nav2_goal_bridge.py          # /goal_pose → NavigateToPose 桥
│
└── utils/
    ├── gpu_gl_env.sh            # NVIDIA Optimus GPU/GL 检测
    ├── ensure_fuel_models.py    # Gazebo Fuel 模型缓存
    ├── normalize_cave_world.py  # cave 世界归一化
    └── test_map_publisher.py    # 地图发布测试
```

### 分层设计

| 层 | 脚本 | 职责 |
|---|---|---|
| **入口层** | `start.sh`, `run_sim_gui.sh` 等 | 设环境默认值 → exec 核心层 |
| **核心仿真层** | `run_sim.sh` | Gazebo 世界、机器人 spawn、Livox/IMU/RViz、点云管线、FAST-LIO2 |
| **导航堆栈层** | `run_mppi.sh`, `run_elevation_mppi.sh` | 在核心仿真之上拉起高程图、通行性图、MPPI、sand MPC、探索节点 |
| **建图层** | `run_gp_fastlio.sh`, `run_gp_nav.sh` | GP 建图 |
| **探索层** | `run_lrae.sh` | LRAE 探索规划器 |
| **构建层** | `build.sh`, `build_fastlio.sh` | colcon 构建 |
| **工具层** | `stop.sh`, `open_depth_camera.sh`, `open_teleop.sh` | 进程管理、运行时传感器、遥控 |
| **Python 节点** | `continuous_navigator.py`, `nav2_goal_bridge.py` | Nav2 辅助节点 |

---

## 2. 调用图

```
start.sh
  └─> run_sim.sh
        ├─ (if MPPI enabled)    ──> run_mppi.sh
        │     ├─ run_sim.sh (内部标记 MAP_SIM_INTERNAL_MPPI_NAVIGATION=1)
        │     ├─ elevation_map_exporter.py
        │     ├─ traversability_to_map.py
        │     ├─ elevation_mapping_node.py
        │     ├─ nav2_mppi.launch.py (launch/)
        │     ├─ sand_mpc_compensator
        │     └─ novelty_explorer
        ├─ (if elev only)       ──> run_elevation_mppi.sh
        │     ├─ run_sim.sh (内部标记 MAP_SIM_INTERNAL_ELEVATION_LAUNCH=1)
        │     ├─ elevation_map_exporter.py
        │     ├─ traversability_to_map.py
        │     ├─ elevation_mapping_node.py
        │     └─ mppi_navigator
        ├─ (if GP default stack)──> run_gp_fastlio.sh
        │     ├─ run_sim.sh (内部标记 MAP_SIM_INTERNAL_DEFAULT_STACK=1)
        │     └─ gp_mapping_node
        └─ (否则) 直接执行 ros2 launch ros2_livox_simulation sim_launch_omni.py

run_sim_gui.sh   ──> run_sim.sh (MAP_SIM_GZCLIENT=1)
run_sim_omni.sh  ──> run_sim.sh (MAP_SIM_BASE_VARIANT=omni)
run_sim_camera.sh ──> run_sim.sh (MAP_SIM_ENABLE_DEPTH_CAMERA=1)
run_fastlio.sh   ──> run_sim.sh (MAP_SIM_ENABLE_FASTLIO2=1)
run_gp_nav.sh    ──> run_sim.sh (GP 建图，无 FAST-LIO)
run_lrae.sh      ──> ros2 launch sim_launch_omni.py + lrae_exploration.py
```

**关键机制**：`run_sim.sh` 通过 `MAP_SIM_INTERNAL_*` 环境变量区分"被上层脚本调用"和"被用户直接调用"。当被上层脚本调用时，设 `MAP_SIM_INTERNAL_*=1` 可以防止 `run_sim.sh` 再次 `exec` 到上层脚本造成无限递归。

---

## 3. 入口层 — 用户直接调用的脚本

### 3.1 `start.sh`

**职责**：项目顶层入口。设默认开关后转给 `run_sim.sh`。

```bash
MAP_SIM_GZCLIENT=1 MAP_SIM_ENABLE_RVIZ=1
MAP_SIM_ENABLE_DEFAULT_STACK=0
MAP_SIM_ENABLE_ELEVATION_MAPPING=1
MAP_SIM_ENABLE_MPPI_NAVIGATION=1
exec run_sim.sh "$@"
```

**默认行为**：开 GUI + RViz，不开 GP default stack，开高程图 + MPPI 导航。即默认进入全链路探索模式。

**调用**：`bash scripts/start.sh` 或 `bash run_sim_local.sh`（`run_sim_local.sh` exec 到 `scripts/start.sh`）。

---

### 3.2 便捷入口脚本

| 脚本 | 设的关键变量 | 用途 |
|---|---|---|
| `run_sim_gui.sh` | `GZCLIENT=1`, `HEADLESS_RENDERING=0`, `ENABLE_RVIZ=1` | 强制 GUI 模式，清除残留的无头环境变量 |
| `run_sim_omni.sh` | `BASE_VARIANT=omni` | 显式选择 omni/swerve 四舵轮变体 |
| `run_sim_camera.sh` | `ENABLE_DEPTH_CAMERA=1`, `GZCLIENT=1` | 深度相机入口（会被 run_sim.sh 的保护逻辑拦住，除非 ALLOW_UNSTABLE=1） |

这些脚本都是 3-10 行的薄封装，只设变量然后 `exec run_sim.sh`。

---

## 4. 核心启动层 — run_sim.sh 深度解析

**文件**：`scripts/run_sim.sh`（496 行）
**角色**：整个工程的核心。负责环境清理、ROS source、世界选择、默认参数分发、launch 文件选择、最终 `ros2 launch`。

### 4.1 工作目录与外部工作区

```
ROOT_DIR = 仓库根目录（= WS_DIR）
ELEV_WS_DIR = ${MAP_SIM_ELEV_WS_DIR:-$ROOT_DIR/tools/elevation_mapping_cupy_ros2_ws}
```

`ELEV_WS_DIR` 是 CuPy 高程图的独立工作区。如果它的 `install/setup.bash` 存在，会在 source 阶段一起 source。

### 4.2 分发逻辑（递归保护）

```bash
# 第 34-51 行
if MAPPI_NAVIGATION enabled and not internal:
    exec run_mppi.sh
if ELEVATION_MAPPING enabled and not internal:
    exec run_elevation_mppi.sh
if DEFAULT_STACK enabled and not internal:
    exec run_gp_fastlio.sh
```

上层脚本调用 `run_sim.sh` 时会设 `MAP_SIM_INTERNAL_*=1`，防止重复分发。

### 4.3 GPU/GL 环境检测

```bash
# 第 53-56 行
if [ -f "$ROOT_DIR/scripts/utils/gpu_gl_env.sh" ]; then
  source "$ROOT_DIR/scripts/utils/gpu_gl_env.sh"
  apply_map_sim_gpu_gl_defaults
fi
```

`apply_map_sim_gpu_gl_defaults()`（定义在 `utils/gpu_gl_env.sh`）：
- 检测 `nvidia-smi` 是否可用
- 尝试 `glxinfo -B` with NVIDIA offload 环境变量
- 如果 NVIDIA OpenGL renderer 被检测到，设置 `__NV_PRIME_RENDER_OFFLOAD=1` 等
- 如果检测失败，回退到默认 OpenGL 路径
- 支持 `MAP_SIM_USE_SOFTWARE_GL=1` 强制软件渲染
- 支持 `MAP_SIM_PREFER_NVIDIA_GL=0` 禁用 NVIDIA 检测

### 4.4 Python/Conda 环境清理 — `sanitize_python_env()`

```bash
unset PYTHONHOME PYTHONPATH CONDA_PREFIX CONDA_DEFAULT_ENV ...
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"
# LD_LIBRARY_PATH 中过滤掉 conda 路径
hash -r
```

**原因**：ROS 2 Humble、Gazebo 插件、conda 三者容易互相污染。表现为 `ros2` 命令异常、Python 包解析错乱、插件动态库加载冲突。

### 4.5 世界选择

#### 地图 ID → 世界文件

```
1 → rm_2026_slam_world.world
2 → apollo15_map_only.world
3 → marsyard2020_map_only.world   ← 默认
4 → marsyard2021_map_only.world
5 → marsyard2022_map_only.world
6 → mars_gazebo_topography_map_only.world
7 / showcase → space_maps_showcase.world
8 / cave / ltu_cave → darpa_cave_01.world
9 / street / autoware → autoware.world
```

#### 默认出生 Z 值

| 世界 | 默认 Z |
|---|---|
| rm_2026_slam_world | 0.19 |
| apollo15_map_only | 0.85 |
| marsyard2020_map_only | 1.60 |
| marsyard2021_map_only | 2.90 |
| marsyard2022_map_only | 2.20 |
| mars_gazebo_topography | 18.0 |
| space_maps_showcase | 0.85 |
| darpa_cave_01 | 0.42 |
| autoware | 0.5 |

#### 默认 Livox 采样参数

- 默认：samples=20000, downsample=1, max_range=70.0
- cave 世界：samples=24000, max_range=42.0

#### 默认光照

- 非 cave / 非 autoware：solar_time=12:00, panel=1
- cave / autoware：solar_time="", panel=0

### 4.6 深度相机保护

```bash
if ENABLE_DEPTH_CAMERA=1 and ALLOW_UNSTABLE_DEPTH_CAMERA!=1:
    echo "[ERR] ..."
    exit 1
```

Gazebo Classic 在此环境下启用 `/livox/depth/*` 会导致 `gzserver`/`gzclient` 崩溃（OGRE 断言）。必须显式设 `ALLOW_UNSTABLE=1` 才能绕过。

### 4.7 端口冲突检测

```bash
GAZEBO_MASTER_PORT=11345
listener=$(describe_tcp_listener $port)
if listener not empty:
    echo "[ERR] Gazebo master port in use"
    exit 1
```

`describe_tcp_listener()` 依次尝试 `lsof` 和 `ss`。

### 4.8 变体选择

```
omni / swerve → sim_launch_omni.py (EXTRA_ARGS=[])
classic / legacy → sim_launch.py (EXTRA_ARGS=["enable_ros2_control:=..."])
```

### 4.9 RViz 配置解析

```bash
if MAP_SIM_RVIZ_CONFIG set:      use it
elif ELEVATION_MAPPING=1:        nexus_elevation_mapping.rviz
else:                             nexus_gazebo_sim.rviz (share/config 相对名)
```

launch 文件中的 `_resolve_rviz_config_path()` 负责把相对名解析到 `pkg_share/config/` 下。

### 4.10 Launch 参数传递

`run_sim.sh` 构建一个 `LAUNCH_ARGS` 数组传给 `ros2 launch`。完整列表（40+ 个参数）见 [环境变量索引](#13-环境变量完整索引)。

条件追加：
- `rviz_config` — 仅当 `MAP_SIM_RVIZ_CONFIG` 非空
- `solar_time` — 仅当 `MAP_SIM_SOLAR_TIME` 非空
- `EXTRA_ARGS` — 变体相关（classic 会加 `enable_ros2_control`）

### 4.11 点云管线

当 `MAP_SIM_ENABLE_POINTCLOUD_PIPELINE=1` 时，launch 文件会启动：
- `/cloud_registered` — 世界坐标系点云
- `/cloud_body` — 车体坐标系点云
- `/cloud_registered_accum` — 累积点云（可选）

### 4.12 FAST-LIO2 集成

当 `MAP_SIM_ENABLE_FASTLIO2=1` 时：
- launch 文件启动 `lio_node`（外部二进制，路径由 `MAP_SIM_FASTLIO2_BIN` 指定）
- 点云管线输入自动切到 `/fastlio2/world_cloud`
- IMU 输入切到 `/imu_fastlio`
- 可选 RViz 配置 `MAP_SIM_FASTLIO2_RVIZ_CONFIG`

---

## 5. 导航堆栈层

### 5.1 `run_mppi.sh` — 全链路探索堆栈

**角色**：在核心仿真之上拉起完整的自主探索链路。

#### 启动顺序

```
1. 后台启动 run_sim.sh（设内部标记防止递归）
   SIM_PID=$!
2. 等待 MAP_SIM_MPPI_BOOT_DELAY（默认 10s）
   → wait_for_sim_startup_or_exit() 在等待期间检查 SIM_PID 是否已退出
3. source ROS + 工作区 + elevation_ws
4. 启动 elevation_map_exporter.py     EXPORT_PID
5. 启动 traversability_to_map.py       TRAV_MAP_PID
6. 启动 elevation_mapping_node.py     ELEV_PID
7. 启动 nav2_mppi.launch.py           MPPI_PID
8. 启动 sand_mpc_compensator          SAND_MPC_PID (可选)
9. 启动 novelty_explorer               EXPLORER_PID (可选)
10. wait $SIM_PID
```

#### cmd_vel 路由

```
sand MPC ON:  Nav2 MPPI → /mppi/cmd_vel_raw → sand_mpc → /cmd_vel → cmd_vel_to_swerve
sand MPC OFF: Nav2 MPPI → /cmd_vel → cmd_vel_to_swerve
```

#### 配置文件

所有节点共用 `config/nexus_navigation_stack.yaml`（可通过 `MAP_SIM_STACK_CONFIG` 覆盖）。各节点可通过 `MAP_SIM_*_CONFIG` 单独指定配置。

#### `wait_for_sim_startup_or_exit()`

```bash
local delay_seconds="${1%.*}"   # 去掉小数部分
local deadline=$((SECONDS + delay_seconds))
while SECONDS < deadline:
    if SIM_PID not running:
        wait SIM_PID → get exit status
        if status==0: sim exited cleanly (unexpected) → return 1
        else: return status (propagate error)
    sleep 1
# deadline 到了再检查一次
if SIM_PID not running: ... return status
```

#### `cleanup()` trap

```bash
trap cleanup EXIT INT TERM
# 对所有子 PID 先 SIGINT，sleep 1，再 SIGTERM，最后 wait
```

#### `append_python_cuda_lib_paths()`

自动找到 `~/.local/lib/python3.X/site-packages/nvidia/*/lib` 和 `torch/lib`，prepend 到 `LD_LIBRARY_PATH`。确保 CuPy / PyTorch 能找到 CUDA 运行时库。

---

### 5.2 `run_elevation_mppi.sh` — CuPy 高程图 + MPPI

与 `run_mppi.sh` 的区别：
- **不含** sand MPC
- **不含** novelty explorer
- MPPI 使用 C++ 版 `mppi_navigator`，不是 Nav2 的 `nav2_mppi_controller`
- boot delay 默认 12s（`run_mppi.sh` 是 10s）
- 不设 `MAP_SIM_INTERNAL_MPPI_NAVIGATION`，而是直接设 `MAP_SIM_INTERNAL_ELEVATION_LAUNCH=1`

---

## 6. GP 建图层

### 6.1 `run_gp_fastlio.sh`

**链路**：FAST-LIO2 → 点云累积 → GP 建图

```bash
MAP_SIM_ENABLE_DEFAULT_STACK=1
MAP_SIM_ENABLE_ELEVATION_MAPPING=0
MAP_SIM_ENABLE_MPPI_NAVIGATION=0
MAP_SIM_ENABLE_FASTLIO2=1
MAP_SIM_ENABLE_POINTCLOUD_PIPELINE=1
MAP_SIM_POINTCLOUD_ACCUMULATE_WORLD=1
```

启动 `run_sim.sh` 后等待 12s，然后启动 `gp_mapping_node`。

GP 建图参数（20+ 个 `-p` 参数）包括：分辨率、inducing points、鲁棒拟合迭代次数、地面种子格大小、浮点拒绝余量等。

### 6.2 `run_gp_nav.sh`

与 `run_gp_fastlio.sh` 类似，但不开 FAST-LIO2。输入 topic 是 `/cloud_registered_accum`（累积点云）。

---

## 7. LRAE 探索层

### 7.1 `run_lrae.sh`

**角色**：启动 NEXUS 仿真 + LRAE 探索规划器。

不使用 `run_sim.sh` 的分发机制，而是直接 `ros2 launch ros2_livox_simulation sim_launch_omni.py`。

#### 启动流程

```
1. 检查 ROS / 工作区 setup.bash
2. sanitize_python_env + configure_render_env
3. 清理旧进程（stop.sh + cleanup_lrae_processes）
4. ros2 launch sim_launch_omni.py (后台) → LIVOX_PID
5. wait_for_topic_once("/nav_odom", 180s)
   → 等 /nav_odom topic 出现（仿真就绪标志）
6. ros2 launch lrae_exploration.py (后台) → LRAE_PID
7. wait -n LIVOX_PID LRAE_PID
   → 任一退出都视为失败
```

#### `configure_render_env()`

- GUI 模式：清除 QT_QPA_PLATFORM / LIBGL_ALWAYS_SOFTWARE
- 无头模式：设 `QT_QPA_PLATFORM=offscreen`、`LIBGL_ALWAYS_SOFTWARE=1`、unset DISPLAY

#### `cleanup_lrae_processes()`

用 `pkill -f` 清理 14 个 LRAE 相关进程模式，包括 sensor_conversion、fitplane、lrae_planner、local_planner、gen_local_goal 等。

### 7.2 `monitor_lrae.sh`

纯监控脚本，不启动任何进程。每 30s 检查一次（共 20 次 = 10 分钟）：
- `/plane_OccMap` 频率
- `/exporation_path` 频率
- `/look_ahead_goal` 频率
- `/cmd_vel` 频率
- 机器人位置变化（用 `bc -l` 算距离）

---

## 8. 已移除能力 — street_infer

`run_street_infer.sh`、`scripts/utils/street_infer.sh`、`src/nexus_semantics/` 和 `tools/Pointcept/`
已在 2026-07-06 从当前工作树移除。当前仓库不再包含点云语义分割 / Pointcept 推理链路。

---

## 9. 构建层

### 9.1 `build.sh`

构建 `livox_ros_driver2` + `ros2_livox_simulation`。

流程：
1. 检查 `/opt/ros/humble/setup.bash`、Livox SDK2 库、livox build.sh
2. `sanitize_python_env`
3. `rosdep update` + `rosdep install`
4. `cd src/livox_ros_driver2 && bash ./build.sh humble`
5. source 工作区
6. `ros2 pkg prefix` 验证两个包可见

### 9.2 `build_fastlio.sh`

单独构建 FAST-LIO2 包到 `install_nexus` / `build_nexus` / `log_nexus` 目录（与主工作区隔离）。

### 9.3 `check_deps.sh`

检查核心文件 + 命令是否存在：
- `/opt/ros/humble/setup.bash`
- `/usr/local/lib/liblivox_lidar_sdk_shared.so`
- `/usr/local/include/livox_lidar_api.h`
- `colcon`, `rosdep`, `gazebo`, `gzserver`, `gzclient`, `xacro`

### 9.4 `install_deps.sh`

`apt install` 一批依赖（ROS 2 Humble、Gazebo、PCL、Boost、pygame 等）。不含 Livox SDK2。

---

## 10. 工具层

### 10.1 `stop.sh` — 进程清理

**角色**：清理所有仿真相关进程。支持 `--dry-run`（只打印不杀）和 `--keep-rviz`（兼容标志，rviz 现已不单独管理）。

#### 匹配模式（`SCOPED_PATTERNS`）

5 大类，覆盖 60+ 个模式：
1. **Launch 包装器**（路径 scoped）：`run_sim.sh`、`run_mppi.sh` 等
2. **ROS 节点可执行名**：`gzserver`、`gzclient`、`rviz2`、`robot_state_publisher`、`spawn_entity.py`、`tf_pub`、Nav2 节点（controller_server, planner_server, bt_navigator 等）
3. **ros2 launch / run 命令**：`ros2 launch ros2_livox_simulation ...`
4. **FAST-LIO / Livox**：`fastlio2`、`livox_ros_driver2`
5. **缓存目录**：`.external_worlds/`、`WORLD_LIGHTING_CACHE_DIR/`

#### 清理流程

```
1. 收集当前进程树 PID（EXCLUDED_PIDS）— 不杀自己
2. 对每个 SCOPED_PATTERN：pgrep -u $UID -f pattern → 收集 PID
3. 过滤掉 EXCLUDED_PIDS 和僵尸进程
4. SIGINT → 等 GRACE_SECONDS(5)
5. SIGTERM → 等 TERM_SECONDS(3)
6. SIGKILL → 等 1s
7. stop_ros2_daemon
8. 清理 PID 文件
9. warn_if_external_gazebo_master_owner — 如果端口还被占，警告
```

#### `collect_process_tree_pids()`

递归收集子进程 PID（通过 `ps -o pid= --ppid`），确保杀掉整个进程树。

#### `is_pid_zombie()`

检查 `ps -o stat=` 是否以 `Z` 开头，跳过僵尸进程。

### 10.2 `open_depth_camera.sh`

在仿真已运行后动态挂载 / 卸载深度相机。

```bash
./open_depth_camera.sh           # 挂载
./open_depth_camera.sh --stop    # 卸载
./open_depth_camera.sh --status  # 查状态
```

调用 `runtime_depth_camera.py`，通过 Gazebo Model Plugin API 在运行时添加 / 删除 sensor。

### 10.3 `open_teleop.sh`

启动 `nexus_teleop` 的 `teleop_gui` 节点。需要 `DISPLAY`。参数包括线速度、横移速度、角速度、发布频率。

---

## 11. Python 节点

### 11.1 `continuous_navigator.py`

连续导航节点，消除探索目标间的停车间隙。

核心机制：
1. `/goal_pose` → `compute_path_to_pose` action 算路径
2. 路径发给 `follow_path` action
3. 机器人行驶中预计算下一个路径
4. 当前路径完成后立即切换预计算的路径 → 零间隙

完全异步（回调内不调用 `spin_until_future_complete`）。

参数：`global_frame`、`robot_frame`、`preplan_distance`(3.0)、`switch_distance`(1.5)、`coast_velocity`(0.3)、`cmd_vel_topic`。

### 11.2 `nav2_goal_bridge.py`

桥接 RViz "2D Goal Pose" 和 novelty_explorer 的 `/goal_pose` 到 Nav2 的 `NavigateToPose` action。

防抖逻辑：如果新目标与当前目标距离 < `GOAL_MIN_SHIFT`(3.0m)，静默丢弃，避免 Nav2 频繁取消重发导致的抖动。

---

## 12. utils/ 子目录

### 12.1 `gpu_gl_env.sh`

NVIDIA Optimus GPU/GL 检测。定义：
- `map_sim_is_truthy()` — 通用 truthy 判断
- `map_sim_detect_nvidia_gl_renderer()` — 用 `glxinfo -B` + NVIDIA offload env 检测
- `apply_map_sim_gpu_gl_defaults()` — 主入口，设 `__NV_PRIME_RENDER_OFFLOAD` 等
- `apply_map_sim_gpu_headless_defaults()` — 无头渲染自动检测

幂等性：通过 `MAP_SIM_GPU_GL_DEFAULTS_APPLIED` 标志防止重复执行。

### 12.2 `ensure_fuel_models.py`

检查 / 下载 Gazebo Fuel 模型到本地缓存目录。

### 12.3 `normalize_cave_world.py`

对 cave 世界 SDF 做坐标归一化（确保 spawn 点不穿模）。

### 12.4 `street_infer.sh`（已移除）

旧的 `street_infer` 兼容 shim 已删除，因为对应的 Pointcept 语义分割链路已从仓库移除。

### 12.5 `test_map_publisher.py`

地图发布测试工具。

---

## 13. 环境变量完整索引

### 仿真核心

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_GZCLIENT` | 1 | 是否启动 gzclient (GUI) |
| `MAP_SIM_ENABLE_HEADLESS_RENDERING` | 0 | 无头渲染 |
| `MAP_SIM_SPAWN_ROBOT` | 1 | 是否 spawn 机器人 |
| `MAP_SIM_SPAWN_X/Y/Z` | 按 world | 出生位置 |
| `MAP_SIM_WORLD` | marsyard2020_map_only.world | 世界文件名 |
| `MAP_SIM_BASE_VARIANT` | omni | 底盘变体 (omni/swerve/classic/legacy) |
| `MAP_SIM_FORCE_CLEAN_START` | 1 | 启动前清理旧进程 |

### 传感器

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_ENABLE_LIVOX` | 1 | Livox 雷达 |
| `MAP_SIM_ENABLE_IMU` | 1 | IMU |
| `MAP_SIM_ENABLE_TF_PUB` | 0 | TF 发布插件 |
| `MAP_SIM_TF_PUB_PUBLISH_NAV_TF` | 1 | TF 插件是否发 nav TF |
| `MAP_SIM_ENABLE_DEPTH_CAMERA` | 0 | 深度相机 |
| `MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA` | 0 | 允许不稳定深度相机 |
| `MAP_SIM_LIVOX_SAMPLES` | 20000 | Livox 采样点数 |
| `MAP_SIM_LIVOX_DOWNSAMPLE` | 1 | Livox 降采样 |
| `MAP_SIM_LIVOX_MAX_RANGE` | 70.0 | Livox 最大量程 (m) |

### 可视化

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_ENABLE_RVIZ` | =$GZCLIENT | 是否启动 RViz |
| `MAP_SIM_RVIZ_CONFIG` | 按模式 | RViz 配置路径 |

### 光照

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_LIGHTING_PRESET` | world | 光照预设 |
| `MAP_SIM_LIGHTING_BRIGHTNESS` | 1.0 | 亮度 |
| `MAP_SIM_SOLAR_TIME` | 12:00 (非 cave) | 太阳时间 |
| `MAP_SIM_ENABLE_SOLAR_TIME_PANEL` | 1 (非 cave) | 太阳时间面板 |

### 点云管线

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_ENABLE_POINTCLOUD_PIPELINE` | 0 (run_sim) / 1 (堆栈) | 点云管线开关 |
| `MAP_SIM_POINTCLOUD_PUBLISH_WORLD` | 1 | 发布世界坐标系点云 |
| `MAP_SIM_POINTCLOUD_PUBLISH_BODY` | 1 | 发布车体坐标系点云 |
| `MAP_SIM_POINTCLOUD_ACCUMULATE_WORLD` | 0 | 累积世界点云 |
| `MAP_SIM_POINTCLOUD_INPUT_TOPIC` | /livox/lidar_PointCloud2 | 输入 topic |
| `MAP_SIM_POINTCLOUD_WORLD_TOPIC` | /cloud_registered | 世界点云 topic |
| `MAP_SIM_POINTCLOUD_BODY_TOPIC` | /cloud_body | 车体点云 topic |
| `MAP_SIM_POINTCLOUD_ACCUM_TOPIC` | /cloud_registered_accum | 累积点云 topic |
| `MAP_SIM_POINTCLOUD_SAVE_PATH` | accumulated_map_ds.pcd | 保存路径 |
| `MAP_SIM_POINTCLOUD_ACCUM_VOXEL` | 0.05 | 累积体素大小 |
| `MAP_SIM_POINTCLOUD_ACCUM_Z_MIN` | 0.05 | 累积 Z 下限 |
| `MAP_SIM_POINTCLOUD_SENSOR_OFFSET_X/Y/Z` | 0/0/0.4 | 传感器偏移 |
| `MAP_SIM_POINTCLOUD_SENSOR_PITCH_DEG` | 30.0 | 传感器俯仰角 |

### FAST-LIO2

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_ENABLE_FASTLIO2` | 0 | FAST-LIO2 开关 |
| `MAP_SIM_FASTLIO2_BIN` | $ROOT_DIR/third_party/FASTLIO2_ROS2/.../lio_node | 二进制路径 |
| `MAP_SIM_FASTLIO2_CONFIG` | $WS/src/nexus_fastlio/config/... | 配置路径 |
| `MAP_SIM_FASTLIO2_NAMESPACE` | /fastlio2 | 命名空间 |
| `MAP_SIM_FASTLIO2_TF_TOPIC` | /fastlio2/tf | TF topic |
| `MAP_SIM_FASTLIO2_LIDAR_INPUT_TOPIC` | /livox/lidar | 雷达输入 |
| `MAP_SIM_FASTLIO2_LIDAR_OUTPUT_TOPIC` | /lidar_fastlio | 雷达输出 |
| `MAP_SIM_FASTLIO2_IMU_INPUT_TOPIC` | /imu_fixed | IMU 输入 |
| `MAP_SIM_FASTLIO2_IMU_OUTPUT_TOPIC` | /imu_fastlio | IMU 输出 |
| `MAP_SIM_FASTLIO2_IMU_LINEAR_ACCEL_SCALE` | 0.1 | 加速度缩放 |
| `MAP_SIM_FASTLIO2_LIDAR_ROTATION_PITCH_DEG` | 30.0 | 雷达旋转 |
| `MAP_SIM_FASTLIO2_IMU_ROTATION_PITCH_DEG` | 30.0 | IMU 旋转 |

### 导航堆栈

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_ENABLE_ELEVATION_MAPPING` | 1 | CuPy 高程图 |
| `MAP_SIM_ENABLE_MPPI_NAVIGATION` | 1 | MPPI 导航 |
| `MAP_SIM_ENABLE_DEFAULT_STACK` | 0 | GP default stack |
| `MAP_SIM_ENABLE_SAND_MPC` | 1 | sand MPC 补偿器 |
| `MAP_SIM_ENABLE_NOVELTY_EXPLORATION` | 1 | novelty 探索 |
| `MAP_SIM_MPPI_BOOT_DELAY` | 10 | MPPI 启动延迟 (s) |
| `MAP_SIM_STACK_CONFIG` | config/nexus_navigation_stack.yaml | 统一配置 |
| `MAP_SIM_ELEVATION_OUTPUT_DIR` | output/elevation_maps/$stamp | 高程图输出 |

### GP 建图

20+ 个 `MAP_SIM_GP_*` 变量控制分辨率、inducing points、鲁棒拟合等。

### 进程清理

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MAP_SIM_STOP_GRACE_SECONDS` | 5 | SIGINT 等待 |
| `MAP_SIM_STOP_TERM_SECONDS` | 3 | SIGTERM 等待 |
| `MAP_SIM_GAZEBO_MASTER_PORT` | 11345 | Gazebo master 端口 |

---

## 14. 进程清理机制

### `run_mppi.sh` / `run_elevation_mppi.sh` 的 cleanup trap

```bash
cleanup() {
  # 按依赖逆序：先 explorer/mppi，后 elevation/sim
  for pid in $EXPLORER $SAND_MPC $MPPI $TRAV_MAP $EXPORT $ELEV $SIM; do
    kill -INT $pid   # 先礼貌
  done
  sleep 1
  for pid in ...; do
    kill $pid        # 再 SIGTERM（kill 默认发 TERM）
  done
  for pid in ...; do
    wait $pid        # 回收
  done
}
trap cleanup EXIT INT TERM
```

### `stop.sh` 的三段式清理

```
SIGINT (5s grace) → SIGTERM (3s) → SIGKILL (1s)
```

排除自身进程树（`collect_excluded_pids` 递归向上找所有父 PID）。

---

## 15. 已知限制与注意事项

### 深度相机不稳定

Gazebo Classic 11 在此环境下启用 `/livox/depth/*` 会触发 OGRE 断言崩溃。默认拦截，需 `MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA=1` 绕过。

### FAST-LIO2 路径

`MAP_SIM_FASTLIO2_BIN` 和 `build_fastlio.sh` 中的 `FASTLIO_WS_DIR` 默认指向 `$ROOT_DIR/third_party/FASTLIO2_ROS2`（仓库内自包含路径）。如需使用外部源码，通过环境变量 `MAP_SIM_FASTLIO2_WS_DIR` / `MAP_SIM_FASTLIO2_BIN` 覆盖。

### CuPy 工作区路径

`ELEV_WS_DIR` 默认 `$ROOT_DIR/tools/elevation_mapping_cupy_ros2_ws`（仓库内自包含路径）。如果不存在，`run_mppi.sh` / `run_elevation_mppi.sh` 会尝试从 `$ROOT_DIR/tools/elevation_ros2/build_elevation_mapping_ros2.sh` 构建。

### conda 环境

当前主线不再依赖仓库内置的 Pointcept conda 运行时。构建和运行仍建议避免让外部 conda 污染 ROS Humble 环境。

### `run_lrae.sh` 独立于 run_sim.sh 分发

`run_lrae.sh` 不经过 `run_sim.sh` 的分发逻辑，直接 `ros2 launch sim_launch_omni.py`。这意味着它不会自动设置 `run_sim.sh` 中的默认环境变量（如 `MAP_SIM_ENABLE_RVIZ`、点云管线参数等），而是自己做了 `configure_render_env()` 和 spawn 设置。

### `monitor_lrae.sh` 路径

脚本使用 `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"` 动态定位仓库根目录，不再硬编码路径。

---

> **文档生成日期**：2026-07-05
> **对应仓库状态**：scripts/ 目录未跟踪（untracked），本文档与 `scripts/` 目录一起提交。

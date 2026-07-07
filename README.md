# NEXUS_GAZEBO_SIM

> **License**: 本项目为专有授权（All Rights Reserved）。详见 [LICENSE](LICENSE) 和 [项目授权声明](LICENSE)。第三方代码归属见 [NOTICE.md](NOTICE.md)。

## NEXUS Logo

本项目内置一个动画版 ASCII logo（旋转 + 3D 文字 + 粒子特效）：

```bash
# 完整动画效果（无限循环，Ctrl+C 退出）
python3 scripts/utils/nexus_logo.py --style golden

# 简短 intro（30 帧 ≈ 1.5 秒，启动时自动播放）
bash scripts/utils/play_logo_intro.sh 30 golden
```

可用风格：`golden` `blackgold` `cyber` `ice` `matrix` `ember` `random`

ROS 2 Humble + Gazebo Classic 11 四舵轮全向机器人仿真工作区。当前主线已经接入：

```text
Livox 仿真雷达
  -> elevation_mapping_cupy 高程图
  -> 高度差通行性 OccupancyGrid
  -> novelty frontier 自动探索
  -> Nav2 MPPI 局部轨迹优化
  -> sand MPC 指令补偿
  -> /cmd_vel
  -> 四舵轮 swerve 控制桥
  -> Gazebo 机器人运动
```

这个 README 按“能把系统重新拉起来并定位问题”为目标写。优先看“快速启动”和“全链路说明”；调参、排障、算法细节在后面。

## 当前状态

- 默认入口已经是完整探索链路：`runlocal/start.sh`、`run_sim_local.sh`、`scripts/start.sh` 最终都会进入 `scripts/run_sim.sh`，再按默认参数转到 `scripts/run_mppi.sh`。
- `scripts/run_mppi.sh` 默认启动：Gazebo、Livox、真值位姿/odom、点云管线、CuPy 高程图、高度差通行图、Nav2 MPPI、sand MPC、novelty explorer。
- MPPI 当前默认使用 Nav2 官方 `nav2_mppi_controller`（Omni 运动模型），通过 `launch/nav2_mppi.launch.py` 拉起 controller_server / planner_server / bt_navigator 等节点。C++ `mppi_navigator` 仍然保留，可通过 `scripts/run_elevation_mppi.sh` 使用（非默认入口）。
- sand MPC 位于 MPPI 后级：Nav2 controller 输出 remap 到 `/mppi/cmd_vel_raw`，sand MPC 输出 `/cmd_vel`。
- 探索节点使用高度差地图做雷达可见区域、novelty map、frontier、Dijkstra 和 goal lock。探索发布 `/goal_pose`，由 `continuous_navigator.py` 接入 Nav2 的 ComputePathToPose + FollowPath 动作。
- 2026-07-03 做过 180 秒 Gazebo 全链路测试：探索持续发 goal/path，MPPI 和 sand MPC 持续出指令，机器人实际运动。

验证记录：

```text
log: output/sim_tests/full_explore_sand_mpc_20260703_175315.log
duration: 180 s
world: marsyard2020_map_only.world
displacement: about 3.53 m
path length: about 31.8 m
goal/path publications: 209
cmd/raw/wheel command: continuous non-zero output
known limitation: 仍有少量 MPPI all-collision 软警告，但不会硬停车
```

严格结论：Gazebo 版已经能闭环探索并驱动车运动；还没有完成和 2D `map_sim/runsim` 同指标 benchmark，所以不能说已经完全达到 2D 仿真的探索效率。

## 快速启动

先清理旧进程：

```bash
cd ~/NEXUS/NEXUS_GAZEBO_SIM
bash scripts/stop.sh
```

推荐的稳定 headless 启动：

```bash
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

带 Gazebo GUI：

```bash
MAP_SIM_GZCLIENT=1 bash scripts/run_mppi.sh
```

从默认 runlocal 入口启动：

```bash
bash runlocal/start.sh
```

停止：

```bash
bash runlocal/stop.sh
# 等价于
bash scripts/stop.sh
```

如果机器有 `DISPLAY=:1` 但 Gazebo GUI 不稳定，优先用 headless：

```bash
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

`scripts/run_sim.sh` 在 headless 模式会清掉 `DISPLAY` 和 `WAYLAND_DISPLAY`，这是为了避免 Gazebo Classic 在错误 X/GLX 环境下 spawn 失败。

## 一句话运行模式

完整自动探索：

```bash
bash scripts/run_mppi.sh
```

完整自动探索，headless：

```bash
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

关掉探索，只保留 MPPI，手动发 `/goal_pose`：

```bash
MAP_SIM_ENABLE_NOVELTY_EXPLORATION=0 bash scripts/run_mppi.sh
```

关掉 sand MPC，让 MPPI 直接发 `/cmd_vel`：

```bash
MAP_SIM_ENABLE_SAND_MPC=0 bash scripts/run_mppi.sh
```

只开 Gazebo + 机器人 + 传感器，不开高程图/MPPI：

```bash
MAP_SIM_ENABLE_MPPI_NAVIGATION=0 \
MAP_SIM_ENABLE_ELEVATION_MAPPING=0 \
MAP_SIM_ENABLE_DEFAULT_STACK=0 \
bash scripts/run_sim.sh
```

只开高程图和通行图，不开 MPPI：

```bash
MAP_SIM_ENABLE_MPPI_NAVIGATION=0 bash scripts/run_elevation_mppi.sh
```

## 工作区结构

```text
NEXUS_GAZEBO_SIM/
├── README.md
├── config/
│   ├── nexus_navigation_stack.yaml   # 高程图/通行图/sand MPC/探索 统一参数
│   └── nav2_mppi_params.yaml          # Nav2 MPPI controller + costmap 参数
├── launch/
│   ├── nav2_mppi.launch.py            # Nav2 栈 launch（controller/planner/bt/...）
│   └── lrae_exploration.py            # LRAE 探索 launch
├── scripts/
│   ├── start.sh                       # 顶层入口
│   ├── run_sim.sh                     # 核心仿真启动
│   ├── run_mppi.sh                    # 全链路（Nav2 MPPI + sand MPC + 探索）
│   ├── run_elevation_mppi.sh          # CuPy 高程图 + C++ mppi_navigator（非默认）
│   ├── run_fastlio.sh                 # FAST-LIO2 便捷启动
│   ├── run_gp_fastlio.sh / run_gp_nav.sh  # GP 建图链路
│   ├── run_lrae.sh / monitor_lrae.sh  # LRAE 探索
│   ├── build.sh / build_fastlio.sh / build_check.sh
│   ├── check_deps.sh / install_deps.sh
│   ├── open_teleop.sh / open_depth_camera.sh
│   └── stop.sh
├── runlocal/
│   ├── start.sh
│   └── stop.sh
├── run_sim_local.sh
├── src/
│   ├── ros2_livox_simulation/
│   ├── livox_ros_driver2/
│   ├── nexus_elevation_mppi/
│   ├── nexus_sand_mpc/
│   ├── nexus_fastlio/
│   ├── nexus_gp_mapping/
│   ├── nexus_teleop/
│   └── third_party/
├── tools/
│   ├── elevation_mapping_cupy_ros2_ws/  # CuPy 高程图工作区（build/install）
│   └── elevation_ros2/                  # 高程图构建辅助脚本
├── docs/
└── output/
    ├── elevation_maps/
    └── sim_tests/
```

核心包：

| 包 | 作用 |
|---|---|
| `ros2_livox_simulation` | Gazebo world、机器人模型、Livox/IMU 插件、controller launch、`cmd_vel_to_swerve` |
| `livox_ros_driver2` | Livox CustomMsg 消息定义和驱动依赖 |
| `nexus_elevation_mppi` | 高程图导出、高度差通行图、novelty explorer、C++ MPPI（C++ MPPI 仅 `run_elevation_mppi.sh` 使用；默认链路用 Nav2 MPPI） |
| `nexus_sand_mpc` | 从 `sand_sim` 迁移来的 sand-slip MPC 指令补偿器 |
| `nexus_fastlio` | FAST-LIO2 仿真适配 |
| `nexus_gp_mapping` | GP 地形建图旧链路 |
| `nexus_teleop` | 遥控和 pose/TF 桥 |

## 系统依赖

已知目标环境：

| 项 | 版本/路径 |
|---|---|
| Ubuntu | 22.04 |
| ROS 2 | Humble |
| Gazebo | Gazebo Classic 11 |
| Nav2 | Humble 官方包（`nav2_controller`、`nav2_planner`、`nav2_bt_navigator` 等） |
| Livox SDK | `/usr/local/lib/liblivox_lidar_sdk_shared.so` |
| CuPy elevation mapping workspace | `$ROOT_DIR/tools/elevation_mapping_cupy_ros2_ws`（即仓库内 `tools/elevation_mapping_cupy_ros2_ws`） |
| Python runtime | 尽量使用 `/usr/bin/python3`，不要让 conda 污染 ROS 环境 |

Python 依赖：

```bash
/usr/bin/python3 -m pip install --user numpy scipy casadi do-mpc
```

如果系统 Python 被 conda 或 `~/.local` 污染，构建/运行前优先设置：

```bash
export PYTHONNOUSERSITE=1
```

注意：`nexus_sand_mpc` 的优化求解使用 `do-mpc` 和 CasADi。它不是手写 MPC 求解器；ROS 节点只负责建模、延迟队列、观测回放和指令封装。

## 构建

完整构建：

```bash
cd ~/NEXUS/NEXUS_GAZEBO_SIM
bash scripts/build.sh
```

只构建当前主线需要的包：

```bash
cd ~/NEXUS/NEXUS_GAZEBO_SIM
export PYTHONNOUSERSITE=1
source /opt/ros/humble/setup.bash
source ~/NEXUS/NEXUS_LIDAR_SIM/NEXUS_GAZEBO_SIM/tools/elevation_mapping_cupy_ros2_ws/install/setup.bash

colcon build \
  --packages-select \
    livox_ros_driver2 \
    ros2_livox_simulation \
    nexus_elevation_mppi \
    nexus_sand_mpc \
    nexus_fastlio \
    nexus_teleop \
    nexus_gp_mapping \
  --symlink-install
```

构建后加载：

```bash
source install/setup.bash
```

常见构建问题：

| 现象 | 处理 |
|---|---|
| `pkgutil.ImpImporter` 相关 setuptools 错误 | `export PYTHONNOUSERSITE=1` |
| 找不到 Livox SDK | 确认 `/usr/local/lib/liblivox_lidar_sdk_shared.so` 和 `/usr/local/include/livox_lidar_api.h` 存在 |
| 找不到 elevation_mapping_cupy | 先构建 `tools/elevation_mapping_cupy_ros2_ws`（仓库内） |
| `do_mpc` 或 `casadi` 找不到 | 给 `/usr/bin/python3` 安装，不要只装在 conda 环境 |

## 启动脚本关系

入口关系如下：

```text
runlocal/start.sh
  -> scripts/start.sh
    -> scripts/run_sim.sh
      -> scripts/run_mppi.sh              # 默认 MAP_SIM_ENABLE_MPPI_NAVIGATION=1
        -> scripts/run_sim.sh             # 内部启动基础仿真
        -> elevation_map_exporter.py
        -> traversability_to_map.py
        -> elevation_mapping_cupy
        -> nav2_mppi.launch.py            # Nav2 栈（controller_server / planner_server / bt_navigator / ...）
        -> continuous_navigator.py        # /goal_pose -> ComputePathToPose + FollowPath
        -> sand_mpc_compensator
        -> novelty_explorer
```

> 如果用 `scripts/run_elevation_mppi.sh`（非默认），则 Nav2 部分替换为 C++ `mppi_navigator`，且不含 sand MPC / novelty explorer。

`scripts/start.sh` 默认参数：

```bash
MAP_SIM_GZCLIENT=1
MAP_SIM_ENABLE_RVIZ=1
MAP_SIM_ENABLE_DEFAULT_STACK=0
MAP_SIM_ENABLE_ELEVATION_MAPPING=1
MAP_SIM_ENABLE_MPPI_NAVIGATION=1
```

因此直接运行：

```bash
bash runlocal/start.sh
```

会走完整探索链路。

## 全链路数据流

```text
Gazebo world
  -> Livox Mid360 plugin
    -> /livox/lidar
    -> /livox/lidar_PointCloud2
      -> elevation_mapping_cupy
        -> /elevation_mapping_node/elevation_map
          -> elevation_map_exporter
            -> output/elevation_maps/<stamp>/*
          -> traversability_to_map
            -> /traversability_map
              -> novelty_explorer
                -> /novelty_explorer/radar_known
                -> /novelty_explorer/novelty_map
                -> /goal_pose
                -> /mppi/reference_path          # 仅 C++ mppi_navigator 消费；Nav2 自规划路径
              -> Nav2 costmap static_layer        # 订阅 /traversability_map
              -> continuous_navigator.py          # /goal_pose -> ComputePathToPose + FollowPath
                -> controller_server               # nav2_mppi_controller (Omni)
                  -> /mppi/cmd_vel_raw             # sand MPC 开启时 remap
                  -> /plan                         # planner_server 全局路径
                    -> sand_mpc_compensator
                      -> /cmd_vel
                        -> cmd_vel_to_swerve
                          -> /steering_position_controller/commands
                          -> /wheel_velocity_controller/commands
                            -> ros2_control
                              -> Gazebo robot
```

位姿和速度来源：

```text
Gazebo truth plugin
  -> /cube_robot/world_pose
  -> /nav_odom
```

当前探索/MPPI 默认用 `/nav_odom` 和 `/cube_robot/world_pose`，这是仿真闭环的稳定基线。后续接真实 SLAM/定位时，应替换为真实 odom/pose 输入。

## 关键 ROS Topics

| Topic | Type | 方向 | 说明 |
|---|---|---|---|
| `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | Gazebo -> ROS | Livox 原生点云 |
| `/livox/lidar_PointCloud2` | `sensor_msgs/msg/PointCloud2` | Gazebo -> ROS | 标准点云 |
| `/livox/imu` | `sensor_msgs/msg/Imu` | Gazebo -> ROS | 原始 IMU |
| `/imu_fixed` | `sensor_msgs/msg/Imu` | ROS -> ROS | 修正时间戳后的 IMU |
| `/cube_robot/world_pose` | `geometry_msgs/msg/PoseStamped` | Gazebo -> ROS | 机器人真值位姿 |
| `/nav_odom` | `nav_msgs/msg/Odometry` | Gazebo -> ROS | 平面 odom |
| `/elevation_mapping_node/elevation_map` | `grid_map_msgs/msg/GridMap` | mapping -> ROS | CuPy 高程图 |
| `/traversability_map` | `nav_msgs/msg/OccupancyGrid` | traversability -> ROS | 高度差通行性地图（Nav2 costmap static_layer 也订阅） |
| `/novelty_explorer/radar_known` | `nav_msgs/msg/OccupancyGrid` | explorer -> ROS | 模拟雷达已知区域 |
| `/novelty_explorer/novelty_map` | `nav_msgs/msg/OccupancyGrid` | explorer -> ROS | novelty/frontier 调试图 |
| `/goal_pose` | `geometry_msgs/msg/PoseStamped` | explorer/user -> Nav2 | 探索目标（continuous_navigator 接入 Nav2） |
| `/mppi/reference_path` | `nav_msgs/msg/Path` | explorer -> ROS | 探索参考路径（仅 C++ mppi_navigator 消费；Nav2 自规划路径不消费） |
| `/plan` | `nav_msgs/msg/Path` | Nav2 planner -> ROS | Nav2 全局规划路径 |
| `/mppi/cmd_vel_raw` | `geometry_msgs/msg/Twist` | Nav2 controller -> MPC | Nav2 controller 速度输出（sand MPC 开启时 remap） |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | MPC/user -> swerve | 最终底盘速度指令 |
| `/steering_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | bridge -> controller | 4 个舵轮转角 |
| `/wheel_velocity_controller/commands` | `std_msgs/msg/Float64MultiArray` | bridge -> controller | 4 个车轮角速度 |
| `/joint_states` | `sensor_msgs/msg/JointState` | controller -> ROS | 关节状态 |

> C++ `mppi_navigator`（`run_elevation_mppi.sh` 模式）额外发布 `/mppi/optimal_path`、`/mppi/reference_path_debug`、`/mppi/terrain_cost_map`，默认 Nav2 模式下不存在这些 topic。

## 核心配置文件

主配置：

```text
config/nexus_navigation_stack.yaml     # 高程图/通行图/sand MPC/探索 统一参数
config/nav2_mppi_params.yaml            # Nav2 MPPI controller + costmap 参数
```

`nexus_navigation_stack.yaml` 给以下节点供参：

```text
/elevation_mapping_node
/elevation_map_exporter
/traversability_to_map
/sand_mpc_compensator
/novelty_explorer
```

`nav2_mppi_params.yaml` 给 Nav2 栈供参（`controller_server`、`planner_server`、`bt_navigator`、`behavior_server`、`smoother_server`、`waypoint_follower`）。

> `nexus_navigation_stack.yaml` 中也保留了一段 `/mppi_navigator` 参数，仅供 `run_elevation_mppi.sh`（C++ 模式）使用，默认 `run_mppi.sh` 不消费它。

如需单独替换某一类参数，可以用环境变量：

| 变量 | 默认 | 作用 |
|---|---|---|
| `MAP_SIM_STACK_CONFIG` | `config/nexus_navigation_stack.yaml` | 高程图/通行图/sand MPC/探索 统一参数 |
| `MAP_SIM_NAV2_PARAMS` | `config/nav2_mppi_params.yaml` | Nav2 MPPI controller + costmap 参数（`run_mppi.sh` 使用） |
| `MAP_SIM_ELEVATION_CONFIG` | `MAP_SIM_STACK_CONFIG` | CuPy 高程图参数 |
| `MAP_SIM_EXPORTER_CONFIG` | `MAP_SIM_STACK_CONFIG` | 高程图导出参数 |
| `MAP_SIM_TRAVERSABILITY_CONFIG` | `MAP_SIM_STACK_CONFIG` | 通行图参数 |
| `MAP_SIM_MPPI_CONFIG` | `MAP_SIM_STACK_CONFIG` | C++ mppi_navigator 参数（仅 `run_elevation_mppi.sh` 使用；`run_mppi.sh` 用 `MAP_SIM_NAV2_PARAMS`） |
| `MAP_SIM_SAND_MPC_CONFIG` | `MAP_SIM_STACK_CONFIG` | sand MPC 参数 |
| `MAP_SIM_EXPLORER_CONFIG` | `MAP_SIM_STACK_CONFIG` | 探索参数 |

示例：

```bash
MAP_SIM_NAV2_PARAMS=/tmp/my_nav2.yaml bash scripts/run_mppi.sh
```

## 算法 1：高度差通行性地图

节点：

```bash
ros2 run nexus_elevation_mppi traversability_to_map
```

输入：

```text
/elevation_mapping_node/elevation_map
```

输出：

```text
/traversability_map
```

算法：

```text
GridMap elevation layer
  -> 解码 circular buffer
  -> 按 OccupancyGrid 坐标系重排
  -> 对每个 cell 取 k x k 邻域
  -> 计算局部 max(height) - min(height)
  -> 映射到 OccupancyGrid:
       0   = free / white
       100 = obstacle / black
       -1  = unknown / gray
  -> NaN-aware median filter
  -> 发布 /traversability_map
```

默认参数：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `kernel_size` | `3` | 局部高度差窗口 |
| `clear_below_m` | `0.04` | 低于该高度差直接视为 free |
| `accumulate_from_m` | `0.05` | 从该高度差开始线性增加占据值 |
| `full_at_m` | `0.10` | 达到该高度差视为 full obstacle |
| `median_filter_size` | `3` | NaN-aware 中值滤波窗口 |
| `unknown_value` | `-1` | 未观测区域 |

这个算法是当前探索和 MPPI 的共享地形基础。它刻意不依赖 CuPy 自带的 CNN traversability 层，而是从 elevation 层直接算高度差，便于和 `map_sim/runsim` 的核心逻辑对齐。

## 算法 2：Novelty Explorer 自动探索

节点：

```bash
ros2 run nexus_elevation_mppi novelty_explorer
```

输入：

```text
/traversability_map
/nav_odom
/cube_robot/world_pose
```

输出：

```text
/goal_pose
/mppi/reference_path
/novelty_explorer/radar_known
/novelty_explorer/novelty_map
```

主逻辑：

```text
高度差 OccupancyGrid
  -> 转内部 UNKNOWN/FREE/OBSTACLE 网格
  -> 从机器人位姿做模拟 radar raycast
  -> radar_known 记录当前可见 free/obstacle
  -> novelty_map 对已观测区域做衰减
  -> 找 free/unknown 边界 frontier
  -> 对候选 frontier 计算安全性、距离、novelty、路径代价
  -> Dijkstra 规划到局部 goal
  -> GoalLock 保持当前目标，处理 arrived/stuck/unreachable/path_jump
  -> 发布 /goal_pose 和 /mppi/reference_path
```

重要对齐点：

- raycast 只被 obstacle 截断，不会因为 unknown cell 直接中断。
- 这是为了和原始 `map_sim/raycasting.py` 保持一致：未知高度图空洞不应该挡住模拟雷达视线。
- `GoalLock.set_goal()` 会重置 stuck 计数和上一帧位置，避免旧目标的 stuck 状态污染新目标。

关键参数：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `planning_rate` | `2.0` | 探索规划频率 |
| `radar_range` | `5.0` | 模拟雷达射线长度 |
| `radar_rays` | `180` | 雷达射线数量 |
| `vision_range` | `1.0` | 近场视野 |
| `vision_fov` | `270.0` | 近场视野角度 |
| `frontier_count` | `30` | 每轮评估的 frontier 数 |
| `frontier_max_dist` | `10.0` | frontier 搜索最大距离 |
| `safe_radius` | `0.08` | 候选点安全半径 |
| `trav_threshold` | `0.22` | 可通行阈值 |
| `arrived_threshold` | `0.2` | 到达目标距离 |
| `stuck_steps` | `3` | 连续多少轮低位移判定 stuck |
| `stuck_disp_threshold` | `0.05` | 每轮最低位移阈值 |
| `enable_unknown_fallback` | `true` | 没有好 frontier 时允许未知 fallback |
| `enable_last_resort_no_los` | `true` | 最后兜底允许无 LOS 候选 |

## 算法 3：Nav2 MPPI 局部导航

默认链路 (`scripts/run_mppi.sh`) 使用 Nav2 官方 `nav2_mppi_controller`，运动模型为 Omni。

启动方式：

```bash
ros2 launch launch/nav2_mppi.launch.py
```

该 launch 文件拉起完整 Nav2 栈：`controller_server` / `planner_server` / `bt_navigator` / `behavior_server` / `smoother_server` / `waypoint_follower` / `lifecycle_manager`，以及 `continuous_navigator.py`（`/goal_pose` → `ComputePathToPose` + `FollowPath` 动作，连续预规划无 stop-and-go）。

配置文件：

```text
config/nav2_mppi_params.yaml
```

输入：

```text
/traversability_map          # Nav2 costmap static_layer 订阅
/nav_odom                    # bt_navigator odom_topic
/goal_pose                   # continuous_navigator 接入
```

输出：

```text
/mppi/cmd_vel_raw            # controller_server remap（sand MPC 开启时）
/cmd_vel                     # sand MPC 关闭时 controller_server 直接输出
/plan                        # planner_server 全局路径
```

MPPI 采样参数（`FollowPath` 下）：

| 参数 | 默认 |
|---|---:|
| `controller_frequency` | `20.0` |
| `batch_size` | `1000` |
| `time_steps` | `56` |
| `model_dt` | `0.05` |
| `iteration_count` | `1` |
| `temperature` | `0.5` |
| `gamma` | `0.015` |
| `motion_model` | `Omni` |
| `retry_attempt_limit` | `1` |

运动约束：

| 参数 | 默认 |
|---|---:|
| `vx_max` | `1.50` |
| `vx_min` | `-0.30` |
| `vy_max` | `0.60` |
| `wz_max` | `1.40` |
| `ax_max` | `3.0` |
| `ay_max` | `2.0` |
| `awz_max` | `3.0` |

代价项（Nav2 Critic scale）：

| Critic | scale | 说明 |
|---|---:|---|
| `ConstraintCritic` | `4.0` | 运动约束 |
| `CostCritic` | `4.0` | costmap 代价（`critical_cost: 5000.0`） |
| `GoalCritic` | `10.0` | 终点距离 |
| `GoalAngleCritic` | `1.5` | 朝向目标 |
| `PathAlignCritic` | `1.5` | 贴近路径 |
| `PathFollowCritic` | `1.5` | 沿路径推进 |
| `PathAngleCritic` | `1.5` | 路径角度 |
| `PreferForwardCritic` | `0.25` | 前进偏好 |
| `TwirlingCritic` | `0.005` | 抑制原地乱转 |
| `ObstaclesCritic` | `3.0` | 障碍代价（`collision_cost: 5000.0`，`inflation_radius: 0.25`） |

costmap 配置：

| 参数 | 值 |
|---|---|
| `local_costmap` `robot_radius` | `0.18` |
| `local_costmap` `inflation_radius` | `0.25` |
| `local_costmap` `static_layer` `map_topic` | `/traversability_map` |
| `global_costmap` `static_layer` `map_topic` | `/traversability_map` |

cmd_vel 路由：

```text
sand MPC ON:  controller_server -> /mppi/cmd_vel_raw -> sand_mpc -> /cmd_vel -> cmd_vel_to_swerve
sand MPC OFF: controller_server -> /cmd_vel -> cmd_vel_to_swerve
```

### C++ mppi_navigator（替代方案）

非默认入口 `scripts/run_elevation_mppi.sh` 使用 C++ `mppi_navigator`（`ros2 run nexus_elevation_mppi mppi_navigator`），源码 `src/nexus_elevation_mppi/src/mppi_navigator.cpp`，参数在 `config/nexus_navigation_stack.yaml` 的 `/mppi_navigator` 段。该节点额外发布 `/mppi/optimal_path`、`/mppi/reference_path_debug`、`/mppi/terrain_cost_map`。`fail_on_all_collision: false` 在所有采样轨迹都碰障碍时不硬停车。

## 算法 4：Sand MPC 指令补偿

节点：

```bash
ros2 run nexus_sand_mpc sand_mpc_compensator
```

源码：

```text
src/nexus_sand_mpc/nexus_sand_mpc/sand_mpc_node.py
src/nexus_sand_mpc/nexus_sand_mpc/sand_mpc_controller.py
```

输入：

```text
/mppi/cmd_vel_raw
/nav_odom
```

输出：

```text
/cmd_vel
```

作用：

```text
MPPI raw Twist
  -> 分解线速度模长 v_ref 和角速度 w_ref
  -> 根据 odom 估计实际 v/w
  -> 估计 slip
  -> do-mpc/CasADi 求解 MIMO MPC
  -> 输出补偿后的 v/w
  -> 恢复原始 lateral 方向
  -> 发布 /cmd_vel
```

默认参数：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `control_rate` | `20.0` | MPC 输出频率 |
| `horizon` | `10` | MPC horizon |
| `dt_nominal` | `0.05` | 离散时间 |
| `cmd_delay` | `0.05` | 指令延迟模型 |
| `drive_tau` | `0.08` | 平动一阶响应 |
| `turn_tau` | `0.08` | 转向一阶响应 |
| `slip_alpha` | `0.15` | slip 估计更新率 |
| `slip_init` | `0.10` | 初始 slip |
| `correction_gain` | `0.25` | odom 观测校正增益 |
| `v_max` | `1.50` | 最大线速度 |
| `w_max` | `1.40` | 最大角速度 |
| `passthrough_on_missing_odom` | `true` | odom 缺失时透传原始指令 |
| `publish_zero_on_timeout` | `true` | 指令超时时发布 0 |

注意：

- 这个 MPC 是库驱动的 do-mpc/CasADi 版本，不是手写求解器。
- 当前用来放在 MPPI 后面做低层指令补偿，不负责全局路径规划。
- 如果 odom 暂时没有，它会透传 `/mppi/cmd_vel_raw`，避免链路完全断掉。

## 算法 5：四舵轮控制桥

节点：

```bash
cmd_vel_to_swerve
```

源码：

```text
src/ros2_livox_simulation/scripts/cmd_vel_to_swerve.py
```

输入：

```text
/cmd_vel
```

输出：

```text
/steering_position_controller/commands
/wheel_velocity_controller/commands
```

默认几何参数：

| 参数 | 默认 |
|---|---:|
| `wheel_radius` | `0.10` |
| `wheelbase` | `0.35` |
| `track_width` | `0.40` |
| `max_wheel_speed` | `18.0` |
| `max_steering_rate` | `5.5` |
| `module_speed_deadband` | `0.10` |
| `publish_rate` | `30.0` |

当前默认用 swerve kinematics。wheel sign 已经按 Gazebo 控制方向修正。

## 地图选择

脚本参数可以选择地图：

```bash
bash scripts/run_mppi.sh 3
bash scripts/run_mppi.sh cave
bash scripts/run_mppi.sh street
```

也可以用环境变量：

```bash
MAP_SIM_WORLD=marsyard2020_map_only.world bash scripts/run_mppi.sh
```

地图列表：

| 选择 | 世界文件 | 备注 |
|---|---|---|
| `1` | `rm_2026_slam_world.world` | 默认 spawn z 0.19 |
| `2` | `apollo15_map_only.world` | 默认 spawn z 0.85 |
| `3` | `marsyard2020_map_only.world` | 默认地图，spawn z 1.60 |
| `4` | `marsyard2021_map_only.world` | spawn z 2.90 |
| `5` | `marsyard2022_map_only.world` | spawn z 2.20 |
| `6` | `mars_gazebo_topography_map_only.world` | spawn z 18.0 |
| `7` / `showcase` | `space_maps_showcase.world` | spawn z 0.85 |
| `8` / `cave` / `ltu_cave` | `darpa_cave_01.world` | cave 场景，Livox range 默认较小 |
| `9` / `street` / `autoware` | `autoware.world` | 街道场景 |

手动设置出生点：

```bash
MAP_SIM_SPAWN_X=1.0 \
MAP_SIM_SPAWN_Y=0.5 \
MAP_SIM_SPAWN_Z=1.6 \
bash scripts/run_mppi.sh
```

## 常用环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MAP_SIM_GZCLIENT` | `1` | 是否打开 Gazebo GUI |
| `MAP_SIM_ENABLE_RVIZ` | `MAP_SIM_GZCLIENT` 或 start 默认 `1` | 是否打开 RViz |
| `MAP_SIM_ENABLE_HEADLESS_RENDERING` | `0` | Gazebo headless rendering |
| `MAP_SIM_ENABLE_MPPI_NAVIGATION` | `1` | 是否启用 MPPI 导航栈（Nav2 或 C++ mppi_navigator） |
| `MAP_SIM_NAV2_PARAMS` | `config/nav2_mppi_params.yaml` | Nav2 MPPI 参数文件（`run_mppi.sh`） |
| `MAP_SIM_ENABLE_ELEVATION_MAPPING` | `1` | 是否启用 CuPy 高程图 |
| `MAP_SIM_ENABLE_NOVELTY_EXPLORATION` | `1` | 是否启用自动探索 |
| `MAP_SIM_ENABLE_SAND_MPC` | `1` | 是否启用 sand MPC |
| `MAP_SIM_ENABLE_DEFAULT_STACK` | `0` | 旧 GP/FastLIO 默认栈 |
| `MAP_SIM_ENABLE_TF_PUB` | `run_mppi` 内部默认 `1` | 真值位姿/odom/TF 发布 |
| `MAP_SIM_TF_PUB_PUBLISH_NAV_TF` | `0` in MPPI path | 是否发布 nav TF |
| `MAP_SIM_ENABLE_POINTCLOUD_PIPELINE` | `1` in MPPI path | 点云转换管线 |
| `MAP_SIM_ENABLE_FASTLIO2` | `0` | 是否启用 FAST-LIO2 |
| `MAP_SIM_WORLD` | `marsyard2020_map_only.world` | 世界文件 |
| `MAP_SIM_MAP` | 空 | 地图编号/别名 |
| `MAP_SIM_MPPI_BOOT_DELAY` | `10` in `run_mppi.sh` | 基础仿真启动后延迟启动算法节点 |
| `MAP_SIM_FORCE_CLEAN_START` | `1` | 启动前自动清旧 Gazebo 进程 |
| `MAP_SIM_GAZEBO_MASTER_PORT` | `11345` | Gazebo master port |
| `MAP_SIM_ELEVATION_OUTPUT_DIR` | `output/elevation_maps/<stamp>` | 高程图导出目录 |
| `MAP_SIM_LIVOX_SAMPLES` | `20000` | Livox 每帧采样数 |
| `MAP_SIM_LIVOX_MAX_RANGE` | `70.0` | Livox 最大距离 |

示例：更稳定的服务器跑法：

```bash
MAP_SIM_GZCLIENT=0 \
MAP_SIM_ENABLE_RVIZ=0 \
MAP_SIM_ENABLE_SOLAR_TIME_PANEL=0 \
MAP_SIM_ENABLE_HEADLESS_RENDERING=1 \
bash scripts/run_mppi.sh
```

## 手动发目标

先关探索：

```bash
MAP_SIM_ENABLE_NOVELTY_EXPLORATION=0 bash scripts/run_mppi.sh
```

另一个终端发 goal：

```bash
source /opt/ros/humble/setup.bash
source ~/NEXUS/NEXUS_GAZEBO_SIM/install/setup.bash

ros2 topic pub --once /goal_pose geometry_msgs/msg/PoseStamped "{
  header: {frame_id: 'world'},
  pose: {
    position: {x: 1.0, y: 0.0, z: 0.0},
    orientation: {w: 1.0}
  }
}"
```

如果用的是默认 Nav2 链路，`/goal_pose` 会被 `continuous_navigator.py` 接入 Nav2 的 `ComputePathToPose` + `FollowPath`，Nav2 自己规划路径。`/mppi/reference_path` 只有 C++ `mppi_navigator` 模式（`run_elevation_mppi.sh`）才消费。

## RViz 观察重点

默认 RViz 配置：

```text
src/nexus_elevation_mppi/config/nexus_elevation_mapping.rviz
```

建议看这些层：

| 显示 | Topic | 目的 |
|---|---|---|
| OccupancyGrid | `/traversability_map` | 高度差通行图是否正常 |
| OccupancyGrid | `/novelty_explorer/radar_known` | 模拟雷达观测是否能展开 |
| OccupancyGrid | `/novelty_explorer/novelty_map` | frontier/novelty 是否在变化 |
| Path | `/mppi/reference_path` | 探索发布的参考路径（Nav2 不消费，仅供调试） |
| Path | `/plan` | Nav2 planner_server 全局规划路径 |
| Path | `/local_plan` | Nav2 controller_server 局部轨迹 |
| OccupancyGrid | `/local_costmap/costmap` | Nav2 局部 costmap |
| TF / RobotModel | `base_link`/robot | 车体姿态和关节 |

> C++ `mppi_navigator` 模式下还可看 `/mppi/optimal_path`、`/mppi/terrain_cost_map`，Nav2 模式下不存在。

## CLI 调试命令

确认节点：

```bash
ros2 node list | sort
```

确认 topic：

```bash
ros2 topic list -t | sort
```

看频率：

```bash
ros2 topic hz /traversability_map
ros2 topic hz /goal_pose
ros2 topic hz /mppi/cmd_vel_raw
ros2 topic hz /cmd_vel
ros2 topic hz /wheel_velocity_controller/commands
ros2 topic hz /plan
```

看一条消息：

```bash
ros2 topic echo --once /goal_pose
ros2 topic echo --once /mppi/cmd_vel_raw
ros2 topic echo --once /cmd_vel
ros2 topic echo --once /nav_odom
```

看 QoS：

```bash
ros2 topic info /traversability_map -v
ros2 topic info /cmd_vel -v
```

看参数：

```bash
ros2 param list /controller_server
ros2 param get /controller_server FollowPath.batch_size
ros2 param get /novelty_explorer radar_range
ros2 param get /sand_mpc_compensator control_rate
```

动态调参示例：

```bash
ros2 param set /controller_server FollowPath.ObstaclesCritic.scale 2.0
ros2 param set /controller_server FollowPath.batch_size 500
ros2 param set /novelty_explorer frontier_max_dist 8.0
```

## 自测流程

构建检查：

```bash
bash -n scripts/run_sim.sh scripts/run_mppi.sh scripts/stop.sh

source /opt/ros/humble/setup.bash
source install/setup.bash
colcon build --packages-select nexus_elevation_mppi nexus_sand_mpc --symlink-install
```

Python 语法检查：

```bash
/usr/bin/python3 -m py_compile \
  src/nexus_elevation_mppi/scripts/traversability_to_map.py \
  src/nexus_elevation_mppi/scripts/novelty_explorer.py \
  src/nexus_elevation_mppi/scripts/elevation_map_exporter.py \
  src/nexus_sand_mpc/nexus_sand_mpc/sand_mpc_controller.py \
  src/nexus_sand_mpc/nexus_sand_mpc/sand_mpc_node.py
```

最小运行检查：

```bash
MAP_SIM_GZCLIENT=0 \
MAP_SIM_ENABLE_RVIZ=0 \
MAP_SIM_ENABLE_NOVELTY_EXPLORATION=1 \
MAP_SIM_ENABLE_SAND_MPC=1 \
bash scripts/run_mppi.sh
```

运行中另开终端检查：

```bash
ros2 topic hz /goal_pose
ros2 topic hz /mppi/cmd_vel_raw
ros2 topic hz /cmd_vel
ros2 topic hz /wheel_velocity_controller/commands
ros2 topic echo --once /nav_odom
```

判断全链路是否活着：

| 检查项 | 期望 |
|---|---|
| `/traversability_map` | 持续发布，宽高非 0 |
| `/novelty_explorer/radar_known` | 有 free/obstacle/unknown 分布 |
| `/goal_pose` | 探索启动后持续/周期性更新 |
| `/plan` | Nav2 planner 有全局路径，poses 非空 |
| `/mppi/cmd_vel_raw` | sand MPC 开启时非全 0 |
| `/cmd_vel` | sand MPC 后非全 0（或 sand MPC 关闭时 controller 直接输出） |
| `/wheel_velocity_controller/commands` | 有轮速输出 |
| `/nav_odom` | 位姿随时间变化 |

## 和 2D map_sim/runsim 的关系

当前 Gazebo 链路不是把 2D 仿真直接搬过来，而是把主干算法语义接入真实仿真：

| 2D `map_sim/runsim` | Gazebo 当前链路 |
|---|---|
| 理想 height/elevation map | `elevation_mapping_cupy` 从 Livox 点云生成 |
| 高度差通行性 | `traversability_to_map.py` |
| raycast radar | `novelty_explorer.py` 中的 radar/vision raycast |
| frontier/novelty | `novelty_explorer.py` |
| local goal/path | `/goal_pose`（Nav2 自规划路径；C++ 模式另有 `/mppi/reference_path`） |
| 2D 运动学执行 | Gazebo 四舵轮 + MPPI + sand MPC |

已经对齐的点：

- raycast 不被 unknown cell 截断。
- 高度差通行图使用局部 height range。
- 探索目标通过 goal lock 保持，不每帧无意义乱跳。
- stuck/unreachable/path_jump 会释放目标并重选。

还没有完全等价的点：

- Gazebo 中有舵轮动力学、控制延迟、地形接触、传感器噪声。
- 高程图来自点云累积，不是 2D 完整真值图。
- MPPI/sand MPC 会影响实际路径，2D 里通常更理想。
- 尚未跑同地图、同起点、同时间的覆盖率 benchmark。

建议后续 benchmark 指标：

| 指标 | 说明 |
|---|---|
| known/free cell coverage | 已探索可通行面积 |
| frontier count over time | frontier 消耗速度 |
| path length | 实际轨迹长度 |
| displacement | 净位移 |
| stuck releases | stuck 触发次数 |
| unreachable releases | unreachable 触发次数 |
| Nav2 recovery 触发次数 | controller 频繁 spin/backup 的压力 |
| command nonzero ratio | 控制输出连续性 |

## 常见问题

### 1. Gazebo spawn 失败

现象：

```text
Service /spawn_entity unavailable
```

处理：

```bash
bash scripts/stop.sh
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

如果 headless 可以，GUI 不行，优先怀疑 X/GLX/显卡环境。

### 2. Gazebo GUI 卡死或 `BadDrawable`

处理：

```bash
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

当前 `run_sim.sh` 在 `MAP_SIM_GZCLIENT!=1` 时会清空 `DISPLAY/WAYLAND_DISPLAY`，避免 Gazebo Classic 误连不可用显示。

### 3. 没有 `/traversability_map`

检查：

```bash
ros2 topic hz /elevation_mapping_node/elevation_map
ros2 topic echo --once /elevation_mapping_node/elevation_map
ros2 topic hz /traversability_map
```

如果高程图没有，先查 Livox 点云：

```bash
ros2 topic hz /livox/lidar_PointCloud2
```

如果 Livox 有但高程图没有，检查 CuPy workspace 是否 source/build。

### 4. 探索不发 goal

检查：

```bash
ros2 topic hz /traversability_map
ros2 topic hz /novelty_explorer/radar_known
ros2 topic hz /goal_pose
ros2 topic echo --once /nav_odom
```

常见原因：

- 通行图全 unknown。
- 机器人 pose/odom 超时。
- `radar_known` 没展开，说明 raycast 或地图坐标有问题。
- frontier 都被判定不可达或不安全。

可临时放宽：

```bash
ros2 param set /novelty_explorer safe_radius 0.08
ros2 param set /novelty_explorer frontier_max_dist 12.0
ros2 param set /novelty_explorer enable_unknown_fallback true
```

### 5. MPPI 有 goal 但车不动

检查链路：

```bash
ros2 topic hz /goal_pose
ros2 topic hz /plan
ros2 topic hz /mppi/cmd_vel_raw
ros2 topic hz /cmd_vel
ros2 topic hz /wheel_velocity_controller/commands
ros2 topic echo --once /mppi/cmd_vel_raw
ros2 topic echo --once /cmd_vel
```

定位：

| 现象 | 可能原因 |
|---|---|
| `/goal_pose` 有，`/plan` 没有 | Nav2 planner 等 costmap/odom，或 goal frame 不对 |
| `/plan` 有，`/mppi/cmd_vel_raw` 没有 | controller_server 等 odom/TF，或 costmap 未就绪 |
| raw 有，`/cmd_vel` 没有 | sand MPC 没启动或崩了 |
| `/cmd_vel` 有，wheel 没有 | `cmd_vel_to_swerve` 或 controller 问题 |
| wheel 有，odom 不动 | Gazebo controller/关节/摩擦问题 |

### 6. Nav2 MPPI 局部代价紧

如果 Nav2 controller 频繁恢复（spin/backup）或轨迹质量差，说明局部 costmap 代价偏紧。可以试：

```bash
ros2 param set /controller_server FollowPath.ObstaclesCritic.scale 2.0
ros2 param set /controller_server FollowPath.CostCritic.scale 3.0
ros2 param set /controller_server FollowPath.ObstaclesCritic.inflation_radius 0.20
```

也可以调高度差图降低障碍密度：

```bash
ros2 param set /traversability_to_map full_at_m 0.12
ros2 param set /traversability_to_map accumulate_from_m  0.06
```

> C++ `mppi_navigator` 模式下的 all-collision 软警告（`fail_on_all_collision: false`）只存在于 `run_elevation_mppi.sh` 链路，默认 Nav2 链路不产生该日志。

### 7. sand MPC 报缺 do-mpc/CasADi

确认系统 Python：

```bash
/usr/bin/python3 - <<'PY'
import casadi
import do_mpc
print("ok")
PY
```

安装：

```bash
/usr/bin/python3 -m pip install --user casadi do-mpc
```

### 8. 停止时出现 `ExternalShutdownException`

如果在 Ctrl-C 或 `scripts/stop.sh` 后看到：

```text
rclpy.executors.ExternalShutdownException
```

这通常是 ROS 2 Python 节点收到 shutdown 后的退出栈，不代表运行中算法崩溃。真正需要处理的是运行阶段反复出现的 exception、节点提前退出、topic 中断或 Gazebo spawn/controller 失败。

### 9. Gazebo master 端口被占用

处理：

```bash
bash scripts/stop.sh
lsof -nP -iTCP:11345 -sTCP:LISTEN
```

如需换端口：

```bash
MAP_SIM_GAZEBO_MASTER_PORT=11346 bash scripts/run_mppi.sh
```

## License

**版权所有 © 2026 Charles。保留所有权利。**

本项目为专有授权（All Rights Reserved）。未经作者书面授权，不得使用、复制、修改、传播、部署或将本项目用于任何商业、比赛、科研、教学或其他用途。完整授权声明见 [LICENSE](LICENSE)。

- 原创代码（`src/nexus_*/`）: All Rights Reserved, Copyright © 2026 Charles
- 第三方代码（`src/third_party/`, `src/livox_ros_driver2/`, `src/ros2_livox_simulation/`）: 保留各自原始许可证，详见 [NOTICE.md](NOTICE.md)

如需授权，请提前联系作者取得书面许可。贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 推荐开发流程

改算法前：

```bash
bash scripts/stop.sh
git status --short
```

改 Python 节点后：

```bash
/usr/bin/python3 -m py_compile <changed_file.py>
colcon build --packages-select <package> --symlink-install
```

改 Nav2 参数或 launch 后：

```bash
bash -n scripts/run_sim.sh scripts/run_mppi.sh scripts/stop.sh
# Nav2 参数改 config/nav2_mppi_params.yaml 后无需构建，重启 run_mppi.sh 即可
```

改 C++ mppi_navigator 后（仅 `run_elevation_mppi.sh` 链路）：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon build --packages-select nexus_elevation_mppi --symlink-install
```

改 launch/script 后：

```bash
bash -n scripts/run_sim.sh scripts/run_mppi.sh scripts/stop.sh
```

跑完整链路：

```bash
MAP_SIM_GZCLIENT=0 MAP_SIM_ENABLE_RVIZ=0 bash scripts/run_mppi.sh
```

停止并确认无残留：

```bash
bash scripts/stop.sh
pgrep -af 'gzserver|gzclient|ros2|controller_server|planner_server|bt_navigator|novelty_explorer|sand_mpc_compensator|cmd_vel_to_swerve'
```

## 当前主要调参入口

通行图 / 探索 / sand MPC 调 `config/nexus_navigation_stack.yaml`；Nav2 MPPI 调 `config/nav2_mppi_params.yaml`：

```text
/traversability_to_map:                      # nexus_navigation_stack.yaml
  kernel_size
  clear_below_m
  accumulate_from_m
  full_at_m
  median_filter_size

/novelty_explorer:                            # nexus_navigation_stack.yaml
  radar_range
  radar_rays
  frontier_count
  frontier_max_dist
  safe_radius
  trav_threshold
  stuck_steps
  stuck_disp_threshold

controller_server / FollowPath:               # nav2_mppi_params.yaml
  batch_size
  time_steps
  model_dt
  vx_max / vy_max / wz_max
  vx_std / vy_std / wz_std
  temperature
  ConstraintCritic.scale
  CostCritic.scale
  GoalCritic.scale
  ObstaclesCritic.scale
  ObstaclesCritic.collision_cost
  ObstaclesCritic.inflation_radius

/sand_mpc_compensator:                        # nexus_navigation_stack.yaml
  horizon
  dt_nominal
  cmd_delay
  drive_tau
  turn_tau
  slip_alpha
  correction_gain
  q_v / q_w
  r_du_v / r_du_w
```

## 何时认为“跑通”

最低标准：

```text
1. Gazebo 成功 spawn 机器人
2. /livox/lidar_PointCloud2 有数据
3. /elevation_mapping_node/elevation_map 有数据
4. /traversability_map 有数据
5. /novelty_explorer/radar_known 有展开
6. /goal_pose 有发布
7. /plan 有 poses（Nav2 planner 输出）
8. /mppi/cmd_vel_raw 非全 0（sand MPC 开启时）
9. /cmd_vel 非全 0
10. wheel/steering controller 有命令
11. /nav_odom 位姿变化
```

工程可用标准：

```text
1. 连续运行 3-5 分钟不崩
2. 机器人净位移明显大于 0
3. 探索 goal/path 持续更新
4. Nav2 controller 没有频繁恢复（spin/backup）
5. stop.sh 能清干净进程
```

算法等价标准：

```text
需要和 2D runsim 做固定地图 benchmark：
同地图、同起点、同时间、同探测半径，
比较覆盖率、路径长度、卡住次数、重复探索比例。
当前还没有完成这一层证明。
```

# NEXUS_GAZEBO_SIM 数据流与技术路线报告

> 生成日期：2026-07-07
> 仓库：`/home/charles/NEXUS/NEXUS_LIDAR_SIM/NEXUS_GAZEBO_SIM`，分支 `main`
> 报告基于实际源码核对（非仅 README 描述）

---

## 一、项目定位

**ROS 2 Humble + Gazebo Classic 11 四舵轮全向机器人自主探索仿真工作区。** 目标是把 2D `map_sim/runsim` 的探索主干算法语义接入真实物理仿真，在 Gazebo 里闭环跑通「感知 → 地形通行性 → frontier 探索 → 局部规划 → 底层补偿 → 舵轮执行」全链路。

核心特征：

- 机器人：四舵轮（swerve）全向底盘，`cmd_vel` → 4 路转向角 + 4 路轮速
- 传感器：Livox Mid360 仿真雷达 + IMU
- 位姿来源：**Gazebo 真值插件**（`/cube_robot/world_pose`、`/nav_odom`），非 SLAM
- 默认地图：`marsyard2020_map_only.world`，spawn z=1.60

---

## 二、系统架构与技术栈

```
┌─────────────────────────────────────────────────────────────┐
│                    Gazebo Classic 11                         │
│  world (*.world) + robot_sim.xacro (urdf) + Livox 插件 +     │
│  ros2_control (steering_position/wheel_velocity 控制器)      │
└──────────────┬──────────────────────────────────────────────┘
               │ /livox/lidar, /livox/lidar_PointCloud2, /livox/imu
               │ /cube_robot/world_pose, /nav_odom, /joint_states
               ▼
┌─────────────────────────────────────────────────────────────┐
│  感知层                                                       │
│  elevation_mapping_cupy (CuPy GPU 高程图)                     │
│   → /elevation_mapping_node/elevation_map (GridMap)          │
│  elevation_map_exporter.py (落盘)                             │
│  traversability_to_map.py (高度差→OccupancyGrid)             │
│   → /traversability_map                                       │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  探索层 (nexus_elevation_mppi/scripts/novelty_explorer.py)   │
│  radar raycast → radar_known → novelty_map → frontier →     │
│  Dijkstra → GoalLock → /goal_pose + /mppi/reference_path     │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  局部规划层 (当前默认: Nav2 官方栈)                           │
│  continuous_navigator.py: /goal_pose → ComputePathToPose +   │
│    FollowPath 动作 (连续预规划, 无 stop-and-go)              │
│  controller_server: nav2_mppi_controller (Omni 运动模型)      │
│  planner_server: NavFn (A*)                                  │
│  behavior_server / smoother / bt_navigator / waypoint_follower│
│  costmap: 静态层订阅 /traversability_map + 膨胀层            │
│   → /mppi/cmd_vel_raw (Sand MPC 开启时) 或 /cmd_vel          │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  底层补偿 (nexus_sand_mpc: do-mpc + CasADi MIMO MPC)         │
│  slip 估计 + 延迟队列 + 观测回放                              │
│   /mppi/cmd_vel_raw → /cmd_vel                               │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  执行层 (ros2_livox_simulation/scripts/cmd_vel_to_swerve.py) │
│  swerve 运动学 → 4 舵轮转角 + 4 轮速                          │
│   → /steering_position_controller/commands                   │
│   → /wheel_velocity_controller/commands                      │
│   → ros2_control → Gazebo 机器人                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、完整数据流（实际运行路径）

以下是基于 `scripts/run_mppi.sh` 实际启动顺序的端到端数据流：

```
[1] Gazebo world 启动
    scripts/run_sim.sh
      → ros2 launch ros2_livox_simulation sim_launch.py
        gzserver + (可选 gzclient)
        spawn robot_sim.xacro (启用 livox + imu + ros2_control)
        controller_manager: steering_position_controller, wheel_velocity_controller

[2] 传感器与真值位姿
    Gazebo Livox 插件
      → /livox/lidar           (livox_ros_driver2/msg/CustomMsg)
      → /livox/lidar_PointCloud2 (sensor_msgs/PointCloud2)
      → /livox/imu             (sensor_msgs/Imu)
    fix_imu_time 节点
      → /imu_fixed            (时间戳修正后 IMU)
    Gazebo 真值插件 (robot_sim.xacro 内)
      → /cube_robot/world_pose (PoseStamped, frame=world)
      → /nav_odom              (Odometry, 平面 odom)

[3] 点云管线 (MAP_SIM_ENABLE_POINTCLOUD_PIPELINE=1)
    CustomMsg → PointCloud2 转换

[4] CuPy 高程图
    ros2 run elevation_mapping_cupy elevation_mapping_node.py
      订阅 /livox/lidar_PointCloud2
      → /elevation_mapping_node/elevation_map (grid_map_msgs/GridMap)
          layers: elevation, variance, traversability
          resolution=0.1, map_length=20m, 5 Hz

[5] 高程图导出 (调试/落盘)
    elevation_map_exporter.py
      → output/elevation_maps/<stamp>/*.mcap + 预览图

[6] 高度差通行性地图
    traversability_to_map.py
      订阅 /elevation_mapping_node/elevation_map
      算法: GridMap elevation 层解码 circular buffer
            → 每个 cell 取 k×k 邻域
            → max(height)-min(height) 映射到 0/100/-1
            → NaN-aware 中值滤波
      → /traversability_map (nav_msgs/OccupancyGrid)

[7] Novelty 自动探索
    novelty_explorer.py
      订阅 /traversability_map, /nav_odom, /cube_robot/world_pose
      算法: 高度差网格 → UNKNOWN/FREE/OBSTACLE
            → 模拟 radar raycast (radar_range=5m, 180 rays, 仅被 obstacle 截断)
            → radar_known 衰减 → novelty_map
            → frontier 提取 + 连通分量加权
            → Dijkstra 规划 (8 邻域, 对角线防穿墙)
            → GoalLock (arrived/stuck/unreachable/path_jump/blacklist/boredom)
            → momentum EMA 方向偏好
      → /novelty_explorer/radar_known (OccupancyGrid)
      → /novelty_explorer/novelty_map  (OccupancyGrid)
      → /goal_pose                     (PoseStamped)
      → /mppi/reference_path           (Path)

[8] Nav2 局部规划 (当前默认, 非 README 描述的 C++ mppi_navigator)
    ros2 launch launch/nav2_mppi.launch.py
      controller_server (nav2_mppi_controller, Omni 运动模型)
        批 1000, horizon 56, dt 0.05, 20 Hz
        critics: Constraint/Cost/Goal/GoalAngle/PathAlign/PathFollow/
                 PathAngle/PreferForward/Twirling/Obstacles
      planner_server (NavFn, A*, allow_unknown)
      behavior_server / smoother_server / bt_navigator / waypoint_follower
      lifecycle_manager (自动启动 lifecycle 节点)
      continuous_navigator.py (TimerAction, 8s 后启动)
        订阅 /goal_pose → ComputePathToPose + FollowPath 动作
        WHILE 行驶中预规划下一段路径 → 切换时零间隔
        (coasting 已禁用: 注释 "unsafe near obstacles")
    costmap: static_layer 订阅 /traversability_map + inflation_layer
      → Nav2 controller 输出
        Sand MPC ON:  /mppi/cmd_vel_raw
        Sand MPC OFF: /cmd_vel

[9] Sand MPC 指令补偿 (MAP_SIM_ENABLE_SAND_MPC=1)
    ros2 run nexus_sand_mpc sand_mpc_compensator
      订阅 /mppi/cmd_vel_raw, /nav_odom
      算法: 分解 v_ref, w_ref
            → odom 估计实际 v/w → 估计 slip (alpha 滤波)
            → do-mpc/CasADi 求解 MIMO MPC (horizon=10, dt=0.05)
              状态: v, w, int_v, int_w, 延迟队列 qv/qw
              控制: u_v, u_w
              tvp: v_ref, w_ref, gain=1-slip
            → 恢复原始 lateral 方向
            → odom 缺失时透传, 超时发 0
      → /cmd_vel (Twist)

[10] 舵轮控制桥
    cmd_vel_to_swerve.py (30 Hz)
      订阅 /cmd_vel
      swerve 运动学: 4 模块 (LF/RF/LR/RR)
        wheelbase=0.35, track_width=0.40, wheel_radius=0.10
        max_wheel_speed=18 rad/s, max_steering_rate=5.5 rad/s
        转角最短角距离 + 速率限制 + 对齐缩放
      → /steering_position_controller/commands (Float64MultiArray ×4)
      → /wheel_velocity_controller/commands    (Float64MultiArray ×4)

[11] ros2_control → Gazebo
    关节控制器 → /joint_states → 机器人运动 → 回到 [2]
```

---

## 四、关键 ROS Topics 全表

| Topic | 类型 | 发布者 → 订阅者 | 频率 |
|---|---|---|---|
| `/livox/lidar` | `livox_ros_driver2/CustomMsg` | Gazebo → 转换器 | ~10 Hz |
| `/livox/lidar_PointCloud2` | `PointCloud2` | 转换器 → CuPy | ~10 Hz |
| `/livox/imu`, `/imu_fixed` | `Imu` | Gazebo → fix → 探索/MPPI | 100 Hz |
| `/cube_robot/world_pose` | `PoseStamped` | Gazebo → 探索/Nav2 | ~50 Hz |
| `/nav_odom` | `Odometry` | Gazebo → 探索/sand MPC | ~50 Hz |
| `/elevation_mapping_node/elevation_map` | `GridMap` | CuPy → 导出/通行图/Nav2 | 5 Hz |
| `/traversability_map` | `OccupancyGrid` | traversability → 探索/Nav2 costmap | ~5 Hz |
| `/novelty_explorer/radar_known` | `OccupancyGrid` | 探索 → RViz | 2 Hz |
| `/novelty_explorer/novelty_map` | `OccupancyGrid` | 探索 → RViz | 2 Hz |
| `/goal_pose` | `PoseStamped` | 探索 → continuous_navigator | 2 Hz |
| `/mppi/reference_path` | `Path` | 探索 → (Nav2 不直接消费) | 2 Hz |
| `/mppi/cmd_vel_raw` | `Twist` | Nav2 controller → sand MPC | 20 Hz |
| `/cmd_vel` | `Twist` | sand MPC → cmd_vel_to_swerve | 20 Hz |
| `/steering_position_controller/commands` | `Float64MultiArray` | swerve → ros2_control | 30 Hz |
| `/wheel_velocity_controller/commands` | `Float64MultiArray` | swerve → ros2_control | 30 Hz |

---

## 五、各算法模块技术细节

### 5.1 高度差通行性地图 (`traversability_to_map.py`, 433 行)

- 输入：CuPy GridMap 的 `elevation` 属性（circular buffer，需解码 + roll）
- 核心：每 cell 取 `kernel_size=3` 邻域，算 `max-min` 高度差
- 映射：`clear_below_m=0.02` → free(0)；`accumulate_from_m=0.04` 线性增；`full_at_m=0.08` → obstacle(100)；未观测 → unknown(-1)
- 后处理：NaN-aware 中值滤波（`median_filter_size=3`）+ 可选 Gaussian
- **刻意不用 CuPy 自带 CNN traversability 层**，为了和 2D `map_sim/runsim` 逻辑对齐

### 5.2 Novelty Explorer (`novelty_explorer.py`, 1245 行)

保留 `map_sim` 主干语义：

- **radar raycast**：仅被 OBSTACLE 截断，不被 unknown 截断（对齐 2D raycasting.py）
- **frontier**：observed-free 且邻接 unobserved 的 cell；按连通分量大小 × 平均 novelty 加权
- **Dijkstra**：8 邻域，对角线移动需两侧均 free（防穿墙）；带 `max_dist` 截断
- **GoalLock** 状态机：`arrived_threshold=0.2`、`stuck_steps=3`×`stuck_disp_threshold=0.05`、`path_jump_ratio=0.5`、blacklist TTL=20、boredom 衰减
- **`set_goal()` 重置 stuck 计数和 `last_robot_xy`**，避免旧目标 stuck 状态污染新目标
- 可视化：`radar_known` + `novelty_map` 两张 OccupancyGrid

### 5.3 局部规划：Nav2 MPPI（当前默认）

⚠️ **见第六节关键发现**。配置 `config/nav2_mppi_params.yaml`：

- `nav2_mppi_controller::MPPIController`，`motion_model: Omni`
- 采样：`batch_size=1000`, `time_steps=56`, `model_dt=0.05`, `iteration_count=1`, `temperature=0.5`, `gamma=0.015`
- 速度约束：`vx_max=1.5, vx_min=-0.3, vy_max=0.6, wz_max=1.4`
- 噪声：`vx_std=0.50, vy_std=0.35, wz_std=0.55`
- 10 个 critic：Goal(10) / GoalAngle(1.5) / PathAlign(1.5) / PathFollow(1.5) / PathAngle(1.5) / Constraint(4) / Cost(4, critical_cost=5000) / Obstacles(3, collision_cost=5000, inflation_radius=0.25) / PreferForward(0.25) / Twirling(0.005)
- costmap：local 10×10m rolling, global 全局, 都订阅 `/traversability_map` 作 static_layer, `robot_radius=0.18`
- planner：`NavfnPlanner`, A*, `allow_unknown=true`

### 5.4 自研 C++ MPPI (`mppi_navigator.cpp`, 2039 行) — 当前非默认

- 仍被 `colcon build` 构建（`install/nexus_elevation_mppi/lib/nexus_elevation_mppi/mppi_navigator` 存在）
- 仍被 `scripts/run_elevation_mppi.sh` 启动
- 参数块仍在 `config/nexus_navigation_stack.yaml` 的 `/mppi_navigator:` 下
- 直接订阅 GridMap + OccupancyGrid + odom + goal + reference_path，自己 rollout
- 支持 Savitzky-Golay 平滑、command_sequence_offset、footprint 采样、动态调参
- **但 `run_mppi.sh`（默认入口）已改用 Nav2**，注释明写 "replaces custom mppi_navigator"

### 5.5 Sand MPC (`sand_mpc_controller.py`, 356 行 + `sand_mpc_node.py`, 213 行)

- 基于 **do-mpc + CasADi**（非手写 QP），MIMO
- 状态：`v, w, int_v, int_w, qv[0..N], qw[0..N]`（N=delay_steps）
- 控制：`u_v, u_w`；时变参数：`v_ref, w_ref, gain=1-slip`
- 一阶响应：`drive_tau=0.08, turn_tau=0.08`；指令延迟 `cmd_delay=0.05`
- slip 估计：`slip_alpha=0.20` 滤波，从 `odom 观测 / 延迟后指令` 反推
- 容错：`passthrough_on_missing_odom=true`，`publish_zero_on_timeout=true`
- IPOPT 求解，`print_level=0`

### 5.6 舵轮控制桥 (`cmd_vel_to_swerve.py`)

- swerve 运动学解算 4 模块转角 + 轮速
- 转角用最短角距离 + `max_steering_rate=5.5` 限速 + `min_alignment_scale=0.35` 对齐缩放
- `module_speed_deadband=0.10` 死区
- wheel sign 已按 Gazebo 控制方向修正

---

## 六、⚠️ 关键发现：README 与实际代码的偏差

核对源码后发现 **README 描述的局部规划器与默认运行路径不一致**：

| 项 | README 描述 | 实际 `run_mppi.sh` |
|---|---|---|
| 局部规划器 | 自研 C++ `mppi_navigator` | **Nav2 官方 `nav2_mppi_controller`** |
| 启动命令 | `ros2 run nexus_elevation_mppi mppi_navigator` | `ros2 launch launch/nav2_mppi.launch.py` |
| 参数文件 | `config/nexus_navigation_stack.yaml` 的 `/mppi_navigator:` 块 | `config/nav2_mppi_params.yaml` |
| 目标消费 | C++ 节点直接订阅 `/goal_pose` | `continuous_navigator.py` 订阅 `/goal_pose` → Nav2 动作 |
| 全局规划 | 无（C++ MPPI 自己跟踪 reference_path） | NavFn (A*) |
| 行为树/恢复 | 无 | bt_navigator + behavior_server |

证据：

- `scripts/run_mppi.sh:264` 注释：`# --- Nav2 MPPI controller (replaces custom mppi_navigator) ---`
- `scripts/run_mppi.sh:281`：`ros2 launch "$ROOT_DIR/launch/nav2_mppi.launch.py"`
- `scripts/run_elevation_mppi.sh:263` 仍用旧路径：`exec ros2 run nexus_elevation_mppi mppi_navigator`
- C++ 节点仍在 `install/` 里（仍被构建），但默认入口不走它

**影响**：

1. `/mppi/reference_path`（探索发布）在 Nav2 路径下**没有被直接消费** —— Nav2 用 NavFn 自己规划路径。探索的 `/goal_pose` 才是实际驱动信号。
2. README 的"算法 3：C++ MPPI"整节描述的是**已退役的默认路径**，仍适用于 `run_elevation_mppi.sh`。
3. 近期提交 `b411377 "Align C++ MPPI navigator defaults with Nav2 MPPI controller"` 和 `6a6b98a "Upgrade C++ MPPI"` 是在维护 C++ 节点，但默认入口已迁到 Nav2 —— 存在双轨维护。

---

## 七、启动脚本关系

```
runlocal/start.sh
  → scripts/start.sh
    → scripts/run_sim.sh
      → 默认 MAP_SIM_ENABLE_MPPI_NAVIGATION=1 时 exec 到 scripts/run_mppi.sh
        → scripts/run_sim.sh (子进程, 启动 Gazebo+机器人+传感器+TF)
        → elevation_mapping_node.py      (ELEV_PID)
        → elevation_map_exporter.py      (EXPORT_PID)
        → traversability_to_map.py       (TRAV_MAP_PID)
        → ros2 launch nav2_mppi.launch.py (MPPI_PID)
        → sand_mpc_compensator           (SAND_MPC_PID, 可关)
        → novelty_explorer               (EXPLORER_PID, 可关)
        → wait $SIM_PID
```

环境变量开关：`MAP_SIM_ENABLE_MPPI_NAVIGATION / ELEVATION_MAPPING / NOVELTY_EXPLORATION / SAND_MPC / DEFAULT_STACK / FASTLIO2 / GZCLIENT / RVIZ`。

---

## 八、当前状态

- **构建**：7 包全绿（`build_check_20260706_212325.log` 显示 23s 完成，仅 C++ 编译 warning）
- **运行**：2026-07-03 有 180s 全链路测试记录（位移 3.53m, 路径 31.8m, 209 次 goal/path 发布），但那是 **C++ mppi_navigator 路径**的记录；Nav2 路径尚无公开 benchmark
- **未完成**：和 2D `map_sim/runsim` 的同地图/同起点/同时间覆盖率 benchmark 未跑
- **Git 状态**：245 处改动未提交，主要是清理旧 `ws/src/livox_ros_driver2` 重复副本和脚本整理

---

## 九、待办建议（按优先级）

1. **同步 README**：把"算法 3"改为 Nav2 MPPI 为默认，C++ mppi_navigator 标为 `run_elevation_mppi.sh` 专用；更新数据流图把 `continuous_navigator.py` + NavFn 纳入
2. **决定双轨去留**：C++ mppi_navigator 和 Nav2 MPPI 二选一，避免双轨参数漂移
3. **跑 Nav2 路径 benchmark**：固定地图 180s+ 测试，记录覆盖率 / path length / stuck 次数
4. **`/mppi/reference_path` 接口**：若走 Nav2，探索发的 reference_path 实际未被用，可考虑删或转 Nav2 path 桥
5. **提交当前 245 处改动**：先 `git status` 分类，把 `ws/src/livox_ros_driver2` 删除等大块清理单独 commit

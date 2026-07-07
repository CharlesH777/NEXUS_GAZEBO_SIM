# NEXUS Gazebo Simulation - Architecture

**文档版本**: 2.0  
**更新日期**: 2026-07-03  
**工作区**: 标准 ROS 2 Humble（扁平工作区，不再嵌套 ws/）

---

## 系统概述

NEXUS_GAZEBO_SIM 是一个基于 Gazebo Classic 11 的四舵轮全向机器人仿真平台，集成：
- Livox MID-360 激光雷达仿真（非重复扫描 + CustomMsg/PointCloud2 双输出）
- CuPy GPU 高程图（elevation + variance + traversability 三层）
- 高度差通行性地图（纯几何，从 elevation 层滑窗 max-min 计算）
- MPPI 轨迹优化导航（batch=384, horizon=20, 10Hz）
- FAST-LIO2 适配（可选）
- GP 高斯过程地形建图（可选）
- LRAE 探索规划框架（可选）

---

## 数据流

### 完整 MPPI 栈（默认）

```
scripts/run_elevation_mppi.sh
  │
  ├─ scripts/run_sim.sh (gzserver + gzclient + RViz)
  │    ├─ robot_state_publisher
  │    ├─ spawn_entity → cube_robot
  │    ├─ spawn_omni_controllers (3 控制器 → active)
  │    ├─ cmd_vel_to_swerve (Twist → 4舵角 + 4轮速)
  │    ├─ fix_imu_time (/livox/imu → /imu_fixed)
  │    └─ [可选] lidar_to_world + cloud_accumulator
  │
  ├─ elevation_mapping_cupy (CuPy GPU, 5Hz)
  │    ← /livox/lidar_PointCloud2
  │    → /elevation_mapping_node/elevation_map (GridMap)
  │
  ├─ elevation_map_exporter (GridMap → npz/pgm 落盘)
  │
  ├─ traversability_to_map (elevation → OccupancyGrid, ~8Hz)
  │    ← /elevation_mapping_node/elevation_map
  │    → /traversability_map
  │
  └─ mppi_navigator (MPPI 优化, 10Hz, 延迟15s启动)
       ← /elevation_mapping_node/elevation_map
       ← /traversability_map
       ← /nav_odom, /cube_robot/world_pose
       ← /goal_pose
       → /cmd_vel
       → /mppi/optimal_path
```

### 控制链路

```
/goal_pose (用户或规划器)
  → MPPI 优化 → /cmd_vel (Twist)
  → cmd_vel_to_swerve (逆运动学)
    → /steering_position_controller/commands [4]
    → /wheel_velocity_controller/commands [4]
    → gazebo_ros2_control → Gazebo 物理
```

---

## 包依赖关系

```
livox_ros_driver2 (消息定义)
  ↑
ros2_livox_simulation (依赖 livox_ros_driver2 + grid_map_msgs)
  ↑ (launch 引用)
nexus_fastlio (独立，被 launch 调用)
nexus_teleop (独立)
nexus_gp_mapping (独立)
nexus_elevation_mppi (依赖 grid_map_msgs, nav_msgs)
```

`grid_map_msgs` 来自 `~/NEXUS/tools/elevation_mapping_cupy_ros2_ws`，不在本工作区内。

---

## 启动顺序（事件驱动）

`sim_launch_omni.py` 的启动顺序：

1. `gzserver` + `gzclient` + `rviz2` 并行启动
2. `robot_state_publisher` 启动
3. **OnProcessStart**(robot_state_publisher) → `spawn_entity.py` 生成机器人
4. **OnProcessExit**(spawn_entity) → 以下节点并行启动：
   - `spawn_omni_controllers` (list → load → configure → activate)
   - `cmd_vel_to_swerve`
   - `fix_imu_time`（如果 IMU 启用）
   - `lidar_to_world` + `cloud_accumulator`（如果点云管线启用）
   - `fastlio_lidar_adapter` + `fastlio_imu_adapter` + `lio_node`（如果 FAST-LIO2 启用）

---

## 通行性地图算法

### 计算（traversability_to_map.py）

```
输入: GridMap 的 elevation 层 (200×200, 0.1m/cell)

Step 1: 解码 + unwrap circular buffer
Step 2: local_height_range_map(kernel_size=3)
         每个 cell 取 3×3 邻域的 max - min 高度差
         (sliding_window_view, NaN-aware)
Step 3: roughness_to_occupancy
         < clear_below_m (0.02)  → 0   (白/可通行)
         0.04 ~ 0.08             → 线性渐变 (灰)
         ≥ full_at_m (0.08)      → 100 (黑/不可通行)
         NaN                      → -1  (灰/未知)
Step 4: median_filter_nan(size=3)  NaN-aware 中值滤波
Step 5: grid_map → OccupancyGrid 坐标变换 (双轴翻转)
```

### 与 CuPy CNN traversability 的区别

| | CuPy CNN traversability | 高度差通行性 |
|---|---|---|
| 来源 | 预训练 CNN (weights.dat) | 纯几何 (max-min) |
| 可调 | 几乎不可调 (权重固定) | 3 个阈值 + kernel_size |
| 车型 | 无关 | 可按车调阈值 |
| 发布层 | GridMap 的 traversability 层 | OccupancyGrid (/traversability_map) |
| 用途 | 库内 drift compensation 安全检查 | RViz 可视化 + MPPI 代价 |

两者并存，不冲突。CuPy 的 traversability 层仍发布在 GridMap 里。

---

## MPPI 导航器参数

关键参数（`config/nexus_navigation_stack.yaml`）：

| 参数 | 值 | 说明 |
|---|---|---|
| batch_size | 384 | 并行采样数 |
| time_steps | 20 | 预测步数 |
| model_dt | 0.10 | 预测步长 |
| vx_max | 1.50 | 最大纵向速度 |
| vy_max | 0.60 | 最大横向速度 |
| wz_max | 1.40 | 最大角速度 |
| traversability_cost_weight | 4.0 | 通行性代价权重 |
| slope_cost_weight | 8.0 | 坡度代价权重 |
| slope_start_deg | 20.0 | 开始惩罚的坡度 |
| slope_max_deg | 45.0 | 完全禁止的坡度 |
| collision_cost | 5000.0 | 碰撞代价 |
| goal_tolerance_xy | 0.35 | 到达容差 |

---

## 构建注意事项

### setuptools 兼容

`~/.local` 里的 setuptools ≥ 74 会破坏 ROS Humble 的 `rosidl_generate_interfaces`。构建时必须：

```bash
export PYTHONNOUSERSITE=1    # 用系统 setuptools 59.6.0
```

运行时**不要**设此变量（`elevation_mapping_cupy` 依赖 `~/.local` 里的 `simple_parsing`）。

### cmake

如果 `~/.local/bin/cmake` 是坏的 pip wrapper，移走它让 `/usr/bin/cmake` 优先。

### livox build.sh

`src/livox_ros_driver2/build.sh` 已修复：只清理 livox 自己的 build 残留，不再 `rm -rf ../../install/`。

### 软件渲染 (llvmpipe)

检测到软件渲染时自动关闭 Gazebo 阴影（`_world_lighting.py` 的 `disable_shadows` 参数），避免 OGRE `AxisAlignedBox` 断言崩溃。RViz 不受影响。

---

## 外部工作区

| 路径 | 内容 |
|---|---|
| `~/NEXUS/tools/elevation_mapping_cupy_ros2_ws/` | CuPy 高程图 + grid_map 消息 |
| `~/NEXUS/NEXUS_LIDAR_SIM/anybotics_elevation_mapping_ws/` | anybotics 高程图（备用） |
| `~/NEXUS/other_sim/map_sim/` | 2D 栅格探索算法仿真（独立） |
| `~/NEXUS/other_sim/sand_sim/` | 沙地滑移 MPC 仿真（独立，待接入） |

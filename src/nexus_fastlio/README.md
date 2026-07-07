# nexus_fastlio

> 专有授权 (All Rights Reserved), Copyright © 2026 Charles. 见 [LICENSE](../../project_identity/legal/LICENSE).

FAST-LIO2 仿真适配节点。本包**不包含** FAST-LIO2 本体（`lio_node` 二进制在外部
`third_party/FASTLIO2_ROS2` 中），只提供把 Gazebo Livox 仿真数据转换成 FAST-LIO2
期望格式的适配器。

## 节点

| 可执行文件 | 语言 | 作用 |
|---|---|---|
| `fastlio_lidar_adapter` | Python | Livox CustomMsg → FAST-LIO2 雷达输入（旋转 pitch、改 frame_id） |
| `fastlio_imu_adapter` | Python | IMU → FAST-LIO2 IMU 输入（加速度缩放、旋转 pitch、改 frame_id） |

## Topics

### fastlio_lidar_adapter

| Topic | 方向 | 类型 | 说明 |
|---|---|---|---|
| `/livox/lidar` | 输入 | `livox_ros_driver2/CustomMsg` | Gazebo 仿真原始 Livox |
| `/lidar_fastlio` | 输出 | `livox_ros_driver2/CustomMsg` | FAST-LIO2 雷达输入 |

### fastlio_imu_adapter

| Topic | 方向 | 类型 | 说明 |
|---|---|---|---|
| `/imu_fixed` | 输入 | `sensor_msgs/Imu` | 时间戳修正后的 IMU |
| `/imu_fastlio` | 输出 | `sensor_msgs/Imu` | FAST-LIO2 IMU 输入 |

## 配置

| 文件 | 说明 |
|---|---|
| `config/fastlio2_sim.yaml` | FAST-LIO2 `lio_node` 的运行参数（雷达范围、体素、IESKF、IMU 噪声、外参） |

## 构建

```bash
source /opt/ros/humble/setup.bash
export PYTHONNOUSERSITE=1

colcon build --packages-select nexus_fastlio --symlink-install
```

依赖 `livox_ros_driver2` 的 `CustomMsg` 消息定义。

## 运行

适配节点由 `scripts/run_sim.sh` 在 `MAP_SIM_ENABLE_FASTLIO2=1` 时自动拉起。
FAST-LIO2 `lio_node` 二进制路径由 `MAP_SIM_FASTLIO2_BIN` 指定。

```bash
# 便捷启动（含 FAST-LIO2 全链路）
bash scripts/run_fastlio.sh

# 或显式开关
MAP_SIM_ENABLE_FASTLIO2=1 bash scripts/run_sim.sh
```

单独启动适配节点：

```bash
source install/setup.bash
ros2 run nexus_fastlio fastlio_lidar_adapter
ros2 run nexus_fastlio fastlio_imu_adapter
```

## 关键参数

| 参数 | 默认 | 说明 |
|---|---:|---|
| `input_topic` | `/livox/lidar` / `/imu_fixed` | 输入 topic |
| `output_topic` | `/lidar_fastlio` / `/imu_fastlio` | 输出 topic |
| `rotation_pitch_deg` | `30.0` | 雷达 / IMU 俯仰旋转角 |
| `linear_accel_scale` | `0.1` | IMU 加速度缩放（适配 Gazebo 量纲） |
| `target_frame_id` | `base_link` | 输出 frame_id |

## 相关文档

- [README.md](../../README.md) — 系统依赖、FAST-LIO2 环境变量
- [SCRIPTS.md](../../SCRIPTS.md) — `run_fastlio.sh` / `build_fastlio.sh` 详解、FAST-LIO2 环境变量索引

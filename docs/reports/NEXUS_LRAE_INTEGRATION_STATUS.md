# NEXUS + LRAE 集成 - 正确方法

## ✅ 当前状态

### 已完成
1. ✅ LRAE 5 个包已复制到 NEXUS_GAZEBO_SIM/ws/src
2. ✅ 所有包成功构建（17 个包）
3. ✅ NEXUS 原始仿真可以启动

### 话题验证
NEXUS 仿真提供：
- `/cloud_registered` - 点云
- `/livox/lidar` - Livox 原始数据  
- `/livox/imu` - IMU 数据
- 需要确认机器人位姿话题名称

---

## 🚀 使用方法

### 步骤 1：启动 NEXUS 仿真

```bash
cd /home/charles/NEXUS/NEXUS_GAZEBO_SIM

# 禁用其他功能，只启动基础仿真
export MAP_SIM_ENABLE_ELEVATION_MAPPING=0
export MAP_SIM_ENABLE_MPPI_NAVIGATION=0
export MAP_SIM_ENABLE_DEFAULT_STACK=0

# 启动仿真
./run_sim_local.sh
```

### 步骤 2：在新终端启动 LRAE

```bash
cd /home/charles/NEXUS/NEXUS_GAZEBO_SIM
source install/setup.bash

# 启动 LRAE 探索
ros2 launch launch_lrae_exploration.py
```

---

## 🔧 需要解决的问题

### 1. 确认机器人位姿话题
LRAE 需要 `/state_estimation` (机器人位姿)

需要检查 NEXUS 发布的位姿话题：
```bash
ros2 topic list | grep -E "pose|odom|state"
```

可能的话题：
- `/odom`
- `/world_pose`  
- `/odometry`
- `/cube_robot/world_pose`

### 2. localPlanner 配置
`localPlanner` 需要路径文件配置。

解决方案：
- 方案 A：不启动 localPlanner（只用 LRAE 探索规划）
- 方案 B：创建所需的路径文件
- 方案 C：修改 localPlanner 使路径文件可选

### 3. 话题映射调整
根据实际的 NEXUS 话题名称调整 `launch_lrae_exploration.py` 中的映射。

---

## 📋 下一步行动

1. **启动 NEXUS 仿真并检查话题**
   ```bash
   ./run_sim_local.sh
   # 新终端
   ros2 topic list
   ros2 topic hz /cloud_registered
   ```

2. **确认机器人位姿话题名称**

3. **调整 launch_lrae_exploration.py 的话题映射**

4. **测试 LRAE 集成**

---

## 📂 文件位置

- **LRAE 包**: `/home/charles/NEXUS/NEXUS_GAZEBO_SIM/ws/src/`
  - fitplane/
  - gen_local_goal/
  - local_planner/
  - lrae_planner/
  - sensor_conversion/

- **Launch 文件**: `/home/charles/NEXUS/NEXUS_GAZEBO_SIM/launch_lrae_exploration.py`

- **文档**: 
  - `README_LRAE_INTEGRATION.md`
  - `NEXUS_LRAE_INTEGRATION_STATUS.md` (本文件)

---

**当前进度**: 70% 完成
- ✅ 包集成
- ✅ 编译成功
- 🔄 话题映射需要调整
- 🔄 需要实际测试

**下一步**: 确认 NEXUS 的机器人位姿话题名称

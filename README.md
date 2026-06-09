# NEXUS_GAZEBO_SIM

`NEXUS_GAZEBO_SIM` 是一个面向二次开发的 bare Gazebo 仿真副本。

它的定位不是“带导航、带建图、带整套上层算法的一站式系统”，而是：

- 保留车体、环境、Gazebo 动力学、ROS 2 接口
- 保留核心传感器接口
  - Livox 雷达
  - IMU
  - 深度相机接口定义
- 保留可视化链路
  - Gazebo GUI
  - RViz
- 去掉导航、FastLIO、FastLIVO 等上层栈
- 让外部算法、控制器、感知模块更容易直接接进来

如果你想把它当成“仿真底座”来接自己的控制、定位、感知、规划，这份 README 就是按这个目标写的。

---

## 1. 这份工程现在是什么

这个仓库现在更接近一个“最小可运行仿真平台”：

- Gazebo 负责世界、物理和传感器模拟
- `robot_state_publisher` 负责把 xacro 展开后的机器人模型发给 ROS
- `spawn_entity.py` 负责把机器人真正生成到 Gazebo 世界里
- `gazebo_ros2_control` 负责把 Gazebo 关节暴露成 ROS 2 控制接口
- `cmd_vel_to_swerve` 负责把外部的 `/cmd_vel` 转成四个舵轮模块的底层关节命令
- `fix_imu_time` 负责把 Gazebo IMU 接口整理成更稳定的外部消费接口
- 可选的 `tf_pub` 插件负责发布世界位姿 / 里程计 / TF

它不再包含：

- `nav2`
- `fast_lio`
- `FAST-LIVO2-ROS2`
- `vikit_common`
- `vikit_ros`
- 依赖这些上层栈的启动脚本和配置

也就是说，这个工程现在只做一件事：

> 提供一个稳定、结构清楚、接口明确的仿真底层，让别的系统接进来。

---

## 2. 推荐理解方式

把整个系统分成 6 层最容易理解：

1. 入口脚本层
   - `build_local.sh`
   - `run_sim_local.sh`
   - `run_sim_local_gui.sh`
   - `run_sim_local_omni.sh`
   - `run_sim_local_camera.sh`
   - `open_depth_camera.sh`

2. Launch 编排层
   - `ws/src/ros2_livox_simulation/launch/sim_launch_omni.py`
   - `ws/src/ros2_livox_simulation/launch/sim_launch.py`

3. 机器人模型层
   - `ws/src/ros2_livox_simulation/urdf/robot_sim_omni.xacro`
   - `ws/src/ros2_livox_simulation/urdf/robot_sim.xacro`
   - `ws/src/ros2_livox_simulation/urdf/depth_camera_gazebo.xacro`

4. 控制与传感器桥接层
   - `ws/src/ros2_livox_simulation/scripts/cmd_vel_to_swerve.py`
   - `ws/src/ros2_livox_simulation/scripts/spawn_omni_controllers.py`
   - `ws/src/ros2_livox_simulation/src/fix_imu_time.cpp`
   - `ws/src/ros2_livox_simulation/src/livox_points_plugin.cpp`
   - `ws/src/ros2_livox_simulation/src/tf_pub.cpp`

5. 可视化配置层
   - `ws/src/ros2_livox_simulation/config/nexus_gazebo_sim.rviz`

6. 外部接入层
   - 你的控制器、规划器、定位器、感知节点
   - 它们通过 topic / TF / odom / spawn service 接进来

---

## 3. 仓库保留了哪些核心内容

### 3.1 ROS 包

当前 `ws/src` 只保留两个包：

- `livox_ros_driver2`
- `ros2_livox_simulation`

这意味着：

- 传感器消息定义还在
- Livox 自定义点云消息还在
- Gazebo 世界、模型、xacro、launch、桥接脚本都还在
- 但上层导航 / 建图 / 融合功能已经不在这个副本里

### 3.2 根目录脚本

- `build_local.sh`
  - 编译仿真工作区
- `run_sim_local.sh`
  - 总入口，负责环境清理、默认参数、地图选择、启动 launch
- `run_sim_local_gui.sh`
  - 显式 GUI 入口
  - 强制打开 `gzclient`
  - 默认同时打开 RViz
- `run_sim_local_omni.sh`
  - 显式选择 omni/swerve 版本的快捷入口
- `run_sim_local_camera.sh`
  - 深度相机快捷入口
  - 但当前默认仍会被保护逻辑拦住，因为 Gazebo Classic 中深度相机不稳定
- `open_depth_camera.sh`
  - 在仿真已经运行后，尝试动态挂一个运行时深度相机
- `runlocal/stop.sh`
  - 清理 Gazebo / launch / runtime camera 相关进程

---

## 4. 整体运行链路

推荐优先记住下面这条主链：

```text
build_local.sh
  -> 构建 livox_ros_driver2 + ros2_livox_simulation

run_sim_local.sh
  -> 清理环境变量
  -> 选择世界 / 默认出生点 / 默认光照 / 默认传感器参数
  -> ros2 launch ros2_livox_simulation sim_launch_omni.py

sim_launch_omni.py
  -> 解析 world
  -> 设置 GAZEBO_MODEL_PATH / GAZEBO_PLUGIN_PATH
  -> xacro 展开 robot_sim_omni.xacro
  -> 启动 gzserver / gzclient
  -> 如果启用可视化，则启动 rviz2 并加载 bare 版 RViz 配置
  -> 启动 robot_state_publisher
  -> 调用 spawn_entity.py 生成 cube_robot
  -> 拉起控制器、/cmd_vel 桥、IMU 整理节点

robot_sim_omni.xacro
  -> 定义底盘
  -> 定义四个舵轮模块
  -> 定义 Livox、IMU、深度相机挂点
  -> 定义 ros2_control 接口
  -> 挂 gazebo_ros2_control 插件
  -> 可选挂 tf_pub 插件
```

这是当前 bare 版本最核心的一条链路。

---

## 5. 构建逻辑到底做了什么

入口文件：`build_local.sh`

### 5.1 构建前检查

它会先检查：

- `/opt/ros/humble/setup.bash` 是否存在
- `/usr/local/lib/liblivox_lidar_sdk_shared.so` 是否存在
- `/usr/local/include/livox_lidar_api.h` 是否存在
- `ws/src/livox_ros_driver2/build.sh` 是否可执行

这一步的目的很简单：

- 不让你在依赖缺失时“看起来像在构建，实际上一定会失败”

### 5.2 Python / conda 去污染

脚本会主动清理：

- `PYTHONHOME`
- `PYTHONPATH`
- `CONDA_PREFIX`
- 以及其他 conda 相关变量

同时还会把 `LD_LIBRARY_PATH` 里明显来自 conda 的路径过滤掉。

这样做是因为：

- ROS 2 Humble 的 Python 环境
- Gazebo 插件加载环境
- 用户自己的 conda 环境

这三者很容易互相污染，表现为：

- `ros2` 命令行为异常
- Python 包解析错乱
- Gazebo / plugin 动态库加载冲突

### 5.3 实际构建动作

构建过程不是在根目录直接 `colcon build`，而是：

1. 进入 `ws/src/livox_ros_driver2`
2. 调用它自带的 `build.sh humble`
3. 构建整个工作区
4. 再 source `ws/install/setup.bash`
5. 最后用 `ros2 pkg prefix` 检查两个包是否真的被 ROS 发现

也就是说，这个脚本不只关心“命令是否跑完”，还关心“包是否真的可见”。

---

## 6. 启动逻辑到底做了什么

入口文件：`run_sim_local.sh`

### 6.1 它的职责

这个脚本负责：

- 清理 Python / conda 环境
- source ROS 和工作区
- 设定默认运行参数
- 选择地图和出生点
- 选择 GUI / headless
- 决定启哪个 launch 文件
- 最终执行 `ros2 launch`

### 6.2 它不是 launch，本质上是“参数整理层”

你可以把它理解成：

- 把一堆 shell 环境变量整理好
- 再统一交给 `sim_launch_omni.py` 或 `sim_launch.py`

### 6.3 它在内部做的关键事情

#### A. 自动判断图形环境是否可能不稳定

如果你开 GUI，它会尝试检测当前 OpenGL 是否落在软件渲染：

- `llvmpipe`
- `Accelerated: no`

如果命中，会提示你：

- 可能卡死
- 建议改成 `MAP_SIM_GZCLIENT=0`

#### B. 地图选择

支持通过数字或别名选世界：

- `1` -> `rm_2026_slam_world.world`
- `2` -> `apollo15_map_only.world`
- `3` -> `marsyard2020_map_only.world`
- `4` -> `marsyard2021_map_only.world`
- `5` -> `marsyard2022_map_only.world`
- `6` -> `mars_gazebo_topography_map_only.world`
- `7` / `showcase` -> `space_maps_showcase.world`
- `8` / `cave` / `ltu_cave` -> `darpa_cave_01.world`

如果你不传任何地图参数，当前默认就是：

- `3` -> `marsyard2020_map_only.world`

#### C. 自动设置默认出生点

不同 world 有不同默认 `z` 值，避免车一生成就埋进地面或者悬空过高。

#### D. 自动设置 Livox 默认采样参数

例如 cave 世界默认点数更高、量程更短，这些都在入口层做了默认值分发。

#### E. 自动设置光照默认参数

例如 cave 场景默认不启太阳时间面板，其它 world 默认启用中午光照。

#### F. 保护深度相机

当前 bare 版保留了深度相机接口定义，但默认禁止直接启用：

- 因为实测 Gazebo Classic 在这个环境里一旦启用 `/livox/depth/*`
- `gzserver` / `gzclient` 可能会因为 OGRE 断言崩掉

所以如果你设置了：

```bash
MAP_SIM_ENABLE_DEPTH_CAMERA=1
```

默认会直接报错退出。

只有显式放开下面这个开关才允许尝试：

```bash
MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA=1
```

#### G. 自动处理 RViz 默认值

现在默认策略是：

- 只要 `MAP_SIM_GZCLIENT=1`
- 就默认 `MAP_SIM_ENABLE_RVIZ=1`

也就是说：

- 主入口 `bash ./run_sim_local.sh` 在桌面环境里会默认打开 Gazebo GUI + RViz
- 如果你只想开 Gazebo，不想开 RViz，可以手动设 `MAP_SIM_ENABLE_RVIZ=0`
- 如果你是 headless，`MAP_SIM_GZCLIENT=0` 时 RViz 也会默认关闭

### 6.4 最终传给 launch 的核心参数

`run_sim_local.sh` 最终会把这些参数传给 launch：

- `world_name`
- `use_gui`
- `enable_headless_rendering`
- `spawn_robot`
- `spawn_x`
- `spawn_y`
- `spawn_z`
- `enable_livox`
- `enable_depth_camera`
- `enable_imu`
- `enable_tf_pub`
- `enable_rviz`
- `rviz_config`
- `lighting_preset`
- `lighting_brightness`
- `solar_time`
- `enable_solar_time_panel`
- `livox_samples`
- `livox_downsample`
- `livox_max_range`

也就是说，根脚本和 launch 之间的边界很清楚：

- 根脚本负责组织参数
- launch 负责按这些参数起系统

---

## 7. 推荐运行模式

### 7.1 默认推荐：GUI + RViz bare 主链

这是现在最推荐、最完整、最稳定的路径：

```bash
bash ./run_sim_local.sh
```

不带参数时默认启动 `3` 号地图，也就是 `marsyard2020_map_only.world`。

如果你想显式表达“我要 GUI 版 bare 仿真”，也可以直接：

```bash
bash ./run_sim_local_gui.sh
```

这两条命令在当前默认配置下都会拉起：

- `gzserver`
- `gzclient`
- `rviz2`

### 7.2 只开 Gazebo GUI，不开 RViz

```bash
MAP_SIM_ENABLE_RVIZ=0 bash ./run_sim_local.sh
```

### 7.3 推荐 headless 验证

如果只是验证系统能不能跑，最稳的是：

```bash
MAP_SIM_GZCLIENT=0 bash ./run_sim_local.sh
```

### 7.4 classic / legacy 版本

根脚本仍保留：

```bash
MAP_SIM_BASE_VARIANT=classic
```

它会走：

- `sim_launch.py`
- `robot_sim.xacro`

这个分支主要用于兼容历史结构。

当前 bare 版本的主文档重点仍然放在：

- omni / swerve 版本

因为：

- 默认也是它
- `/cmd_vel` 控制桥也主要是它
- 当前实际验证最充分的也是它

---

## 8. Launch 层内部逻辑

关键文件：`ws/src/ros2_livox_simulation/launch/sim_launch_omni.py`

这个文件是整个系统的“编排器”。

### 8.1 它做的事情按顺序是

1. 解析 world 路径
2. 解析光照参数
3. 解析 `enable_livox` / `enable_depth_camera` / `enable_imu` / `enable_tf_pub`
4. 展开 `robot_sim_omni.xacro`
5. 组装 `GAZEBO_MODEL_PATH`
6. 组装 `GAZEBO_PLUGIN_PATH`
7. 启动 `gzserver`
8. 如果 GUI 开启，再启动 `gzclient`
9. 如果 `enable_rviz=1`，解析 RViz 配置并启动 `rviz2`
10. 如果允许 solar panel，再延迟起 `solar_time_panel`
11. 启动 `robot_state_publisher`
12. 当 `robot_state_publisher` 启动后，调用 `spawn_entity.py`
13. 当 `spawn_entity.py` 成功退出后，再启动：
    - `spawn_omni_controllers`
    - `cmd_vel_to_swerve`
    - `fix_imu_time`（如果 IMU 开启）

这个事件顺序非常重要，因为它避免了常见的时序问题：

- 机器人还没生成就去找控制器
- `robot_description` 还没准备好就调用 spawn
- `/controller_manager` 还没出现就去配置控制器

### 8.2 RViz 是怎么接进主链的

当前 RViz 不是 shell 层随便再开一个窗口，而是由 launch 层正式托管。

这样做的好处是：

- 生命周期跟仿真主链一致
- `use_sim_time` 能统一继承
- 可以用 `MAP_SIM_RVIZ_CONFIG` 或 launch 参数 `rviz_config:=...` 替换自己的显示布局
- 以后如果你想接别的可视化节点，也可以按同样方式挂进去

默认 RViz 配置文件是：

- `ws/src/ros2_livox_simulation/config/nexus_gazebo_sim.rviz`

它当前主要展示：

- `RobotModel`
- `TF`
- `/livox/lidar_PointCloud2`
- 预留但默认关闭的 `/livox/depth/points`

### 8.3 Launch 事件顺序的核心思想

它不是“所有节点一口气并发起”，而是：

```text
robot_state_publisher 启动
  -> spawn_entity
    -> spawn 完成后
      -> 控制器 / 控制桥 / IMU整理节点
```

这让启动稳定性高很多。

---

## 9. 机器人模型层到底定义了什么

关键文件：`ws/src/ros2_livox_simulation/urdf/robot_sim_omni.xacro`

这个文件不是单纯的几何模型，它同时定义了：

- 机器人结构
- 关节接口
- Gazebo 传感器
- ros2_control 接口
- 可选 TF / odom 插件

### 9.1 底盘结构

它定义了：

- `base_footprint`
- `base_link`
- 四个舵轮模块
  - `left_front`
  - `right_front`
  - `left_rear`
  - `right_rear`

每个模块由两部分组成：

- 转向关节 `*_steer_joint`
- 车轮关节 `*_wheel_joint`

所以从控制角度看：

- 4 个位置控制关节
- 4 个速度控制关节

### 9.2 Livox 挂载

默认挂在：

- `livox_mount_link`

如果启用了 `enable_livox_yaw_follow`，还会多一个：

- `livox_yaw_joint`
- `livox_yaw_link`

让传感器朝向可以根据速度方向动态调整。

### 9.3 深度相机挂点

即使默认不开深度相机，挂点仍保留：

- `depth_camera_mount_link`

这样外部系统要挂自己的相机、或运行时加相机，不需要再改底盘主体结构。

### 9.4 IMU 挂载

IMU 定义在：

- `imu_link`

并固定连接到：

- `livox_mount_link`

这样做的一个重要目的就是：

- 保持 `/livox/imu` 这个接口语义稳定

即使你未来替换上层算法，只要 IMU 仍想和 Livox 坐标关系保持一致，就不需要再改接口。

---

## 10. ros2_control 层到底怎么接上去的

关键文件：

- `robot_sim_omni.xacro`
- `config/cube_rob_omni_ctrl.yaml`
- `scripts/spawn_omni_controllers.py`

### 10.1 Xacro 里声明了哪些关节接口

在 `<ros2_control name="GazeboSystem" type="system">` 里声明：

- 4 个转向关节使用 `position` command interface
- 4 个车轮关节使用 `velocity` command interface

也就是：

| 关节类型 | 命令接口 | 用途 |
| --- | --- | --- |
| `*_steer_joint` | `position` | 决定舵轮朝向 |
| `*_wheel_joint` | `velocity` | 决定车轮转速 |

### 10.2 Gazebo 如何接入 ros2_control

在 xacro 里挂了：

```xml
<plugin name="gazebo_ros2_control" filename="libgazebo_ros2_control.so">
```

并把参数文件指向：

- `config/cube_rob_omni_ctrl.yaml`

所以 Gazebo world 一旦把机器人生出来，就会自动把这些关节注册进 `/controller_manager`。

### 10.3 控制器参数文件的作用

`cube_rob_omni_ctrl.yaml` 里定义了 3 个控制器：

- `joint_state_broadcaster`
- `steering_position_controller`
- `wheel_velocity_controller`

含义分别是：

- `joint_state_broadcaster`
  - 发布所有状态接口
- `steering_position_controller`
  - 收四个舵向角命令
- `wheel_velocity_controller`
  - 收四个车轮速度命令

### 10.4 控制器为什么不是 launch 直接全起

因为 `/controller_manager` 什么时候就绪，取决于：

- Gazebo 插件是否已经真正加载完
- 机器人是否已经被 spawn 到 world

所以这里单独写了 `spawn_omni_controllers.py`，它会按状态机做：

1. `list`
2. `load`
3. `configure`
4. `switch activate`
5. 打印最终状态

比“盲发 spawner 命令”更稳。

---

## 11. 控制接口总览

这是外部系统最需要记住的一张表。

### 11.1 推荐的高层控制入口

| 接口 | 类型 | 方向 | 谁发布 | 谁消费 | 用途 |
| --- | --- | --- | --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 输入 | 你的控制器 | `cmd_vel_to_swerve` | 推荐的主控制入口 |

### 11.2 中间层底盘控制接口

| 接口 | 类型 | 方向 | 谁发布 | 谁消费 | 用途 |
| --- | --- | --- | --- | --- | --- |
| `/steering_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | 输入 | `cmd_vel_to_swerve` 或你的低层控制器 | `steering_position_controller` | 4 个舵轮转向角 |
| `/wheel_velocity_controller/commands` | `std_msgs/msg/Float64MultiArray` | 输入 | `cmd_vel_to_swerve` 或你的低层控制器 | `wheel_velocity_controller` | 4 个车轮角速度 |

### 11.3 状态接口

| 接口 | 类型 | 方向 | 用途 |
| --- | --- | --- | --- |
| `/joint_states` | `sensor_msgs/msg/JointState` | 输出 | 常规关节状态消费 |
| `/dynamic_joint_states` | `control_msgs/msg/DynamicJointState` | 输出 | ros2_control 更完整的状态接口 |

### 11.4 兼容 classic 版本的接口

如果走 `MAP_SIM_BASE_VARIANT=classic`，则更核心的是：

| 接口 | 类型 | 方向 | 用途 |
| --- | --- | --- | --- |
| `/rear_wheel_velocity_controller/commands` | `std_msgs/msg/Float64MultiArray` | 输入 | classic 版本车轮速度控制 |

但当前推荐你优先使用 omni 版本，不建议把新功能主要接在 classic 分支上。

---

## 12. `/cmd_vel` 到车轮命令，内部到底怎么实现

关键文件：`ws/src/ros2_livox_simulation/scripts/cmd_vel_to_swerve.py`

这是当前 bare 版最重要的控制桥。

### 12.1 它的职责

它把：

- 外部系统发布的 `/cmd_vel`

转成：

- 四个舵向角
- 四个车轮角速度

再分别发到：

- `/steering_position_controller/commands`
- `/wheel_velocity_controller/commands`

### 12.2 输入输出关系

输入：

- `geometry_msgs/msg/Twist`
  - `linear.x`
  - `linear.y`
  - `angular.z`

输出：

- `Float64MultiArray[4]` 舵向角
- `Float64MultiArray[4]` 车轮角速度

### 12.3 内部核心计算

对于每个轮模块位置 `(x_i, y_i)`，它先算该模块在车体坐标系下应有的速度向量：

```text
v_ix = v_x - w_z * y_i
v_iy = v_y + w_z * x_i
```

然后求：

```text
speed_i = sqrt(v_ix^2 + v_iy^2) / wheel_radius
angle_i = atan2(v_iy, v_ix)
```

也就是：

- `angle_i` 是舵轮要朝向哪里
- `speed_i` 是车轮要转多快

### 12.4 它还做了哪些工程化处理

#### A. 小速度死区

如果某个模块速度太小，小于 `module_speed_deadband`，它会：

- 保持当前角度不动
- 车轮速度置零

这样可以避免低速抖动。

#### B. 全轮归一化限幅

如果四个轮里有任意一个轮速超过 `max_wheel_speed`，它不会只截断一个轮，而是按比例缩放全部轮速。

好处是：

- 保持运动方向一致
- 不会因为单个轮饱和让整体运动变形

#### C. 180 度翻转优化

如果目标舵向和当前舵向差太大，超过 90 度，它会：

- 把目标角度加 180 度
- 同时把轮速取反

等价于：

- 不用让舵轮大幅转过去
- 直接反向滚动轮子更快

这在舵轮系统里非常常见，也很关键。

#### D. 转向速率限制

每个周期允许的最大转向变化量是：

```text
max_steer_step = max_steering_rate / publish_rate
```

这能避免：

- 目标角度一步跳太大
- Gazebo 里出现不自然的急剧转向

#### E. 转向未对齐时降低驱动输出

它会根据“当前命令角”和“真正目标角”的残差，计算一个 `alignment_scale`：

- 角度没对齐时，减小车轮速度
- 角度越接近，速度越接近原始目标

这样可以避免：

- 舵轮还没摆正，轮子就全速拖着横向打滑

这是整个控制桥里非常重要的一个工程细节。

#### F. 命令超时保护

如果超过 `command_timeout` 没收到新的 `/cmd_vel`，它会自动输出零命令。

作用是：

- 外部控制器死掉时，机器人不会一直沿着旧命令跑

### 12.5 这意味着外部系统该怎么接

如果你是：

- 路径跟踪器
- 遥操作器
- 强化学习策略
- MPC
- 视觉伺服节点

最推荐的接法就是：

> 只发 `/cmd_vel`，不要直接碰四个舵轮控制器。

因为：

- 舵轮分解
- 转向限速
- 角度翻转
- 未对齐减速

这些内部逻辑已经替你做了。

---

## 13. 如果你不想发 `/cmd_vel`，而想直接控底层，应该怎么做

有两种情况。

### 13.1 你要自己做低层舵轮控制

这时你应该直接发布：

- `/steering_position_controller/commands`
- `/wheel_velocity_controller/commands`

但要注意：

- `cmd_vel_to_swerve` 默认也会往这两个 topic 发命令
- 如果你不关闭它，你和它会抢同一组控制器

### 13.2 正确做法

推荐二选一：

1. 复制一份 `sim_launch_omni.py`，把 `cmd_vel_to_swerve` 节点移掉
2. 或者在你的专用 launch 里不要起 `cmd_vel_to_swerve`

不推荐：

- 一边保留 `cmd_vel_to_swerve`
- 一边自己也往控制器 topic 发

因为结果会不可预测。

---

## 14. 传感器接口总览

### 14.1 Livox 雷达接口

| 接口 | 类型 | 用途 |
| --- | --- | --- |
| `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | Livox 风格原生点云 |
| `/livox/lidar_PointCloud2` | `sensor_msgs/msg/PointCloud2` | 标准 ROS 点云接口 |

关键文件：

- `src/livox_points_plugin.cpp`
- `urdf/mid360.xacro`

实现逻辑：

- Gazebo 的 ray sensor 插件被扩展为 `LivoxPointsPlugin`
- 同一次扫描同时构造两种消息
  - `CustomMsg`
  - `PointCloud2`
- 所以外部系统可以按需求任选一种接

推荐接法：

- 你自己的 Livox 风格算法：订阅 `/livox/lidar`
- 通用 ROS / PCL 算法：订阅 `/livox/lidar_PointCloud2`

### 14.2 IMU 接口

| 接口 | 类型 | 用途 |
| --- | --- | --- |
| `/livox/imu` | `sensor_msgs/msg/Imu` | Gazebo 原始 IMU 输出 |
| `/imu_fixed` | `sensor_msgs/msg/Imu` | 经 `fix_imu_time` 整理后的 IMU 输出 |

关键文件：

- `robot_sim_omni.xacro`
- `src/fix_imu_time.cpp`

`fix_imu_time` 当前默认做的事情：

- 订阅 `/livox/imu`
- 发布 `/imu_fixed`
- 当前默认不做旋转修正
- 当前默认不做时间偏移

但它保留了下面这些可扩展参数：

- `timestamp_offset_sec`
- `apply_rotation`
- `rotation_pitch_deg`

所以如果以后你接入：

- 真机对齐标定
- 坐标系修正
- 时间戳补偿

你不必重写整个 IMU 链，只要调这个节点或改它参数即可。

### 14.3 深度相机接口

保留的接口定义：

| 接口 | 类型 |
| --- | --- |
| `/livox/depth/image_raw` | `sensor_msgs/msg/Image` |
| `/livox/depth/camera_info` | `sensor_msgs/msg/CameraInfo` |
| `/livox/depth/depth/image_raw` | `sensor_msgs/msg/Image` |
| `/livox/depth/depth/camera_info` | `sensor_msgs/msg/CameraInfo` |
| `/livox/depth/points` | `sensor_msgs/msg/PointCloud2` |

关键文件：

- `urdf/depth_camera_gazebo.xacro`
- `open_depth_camera.sh`
- `scripts/runtime_depth_camera.py`

当前状态要明确说明：

- 接口定义保留了
- 参数通道保留了
- 运行时动态挂相机的工具也保留了
- 但默认不建议启用

原因不是接口没做，而是：

- 这个 Gazebo Classic 环境里深度相机插件会触发不稳定崩溃

所以这个 bare 版对深度相机的设计是：

- 保留接口形状
- 保留未来接入点
- 当前稳定主链默认不用它

---

## 15. 可选位姿 / TF / odom 接口

关键文件：

- `robot_sim_omni.xacro`
- `src/tf_pub.cpp`

默认：

- `MAP_SIM_ENABLE_TF_PUB=0`

开启后会挂载 `libtf_pub.so` 插件。

### 15.1 它会发布什么

| 接口 | 类型 | 说明 |
| --- | --- | --- |
| `/cube_robot/world_pose` | `geometry_msgs/msg/PoseStamped` | 机器人世界位姿 |
| `/livox/world_pose` | `geometry_msgs/msg/PoseStamped` | Livox 世界位姿 |
| `/nav_odom` | `nav_msgs/msg/Odometry` | 平面化里程计 |
| `/odom` | `nav_msgs/msg/Odometry` | legacy 风格里程计 |
| `odom -> base_footprint` | TF | 平面 TF |

### 15.2 它内部怎么计算

`tf_pub` 会：

1. 从 Gazebo 读取 `model_->WorldPose()`
2. 读取 `/clock`
3. 用模型姿态计算：
   - 完整世界位姿
   - 仅 yaw 的平面姿态
4. 发布：
   - `/cube_robot/world_pose`
   - `/nav_odom`
   - `/odom`
   - TF

### 15.3 适合谁接

适合这些外部模块：

- 想拿真值位姿做评估的算法
- 想拿平面里程计当输入的控制器
- 想做 Teacher / Student 或 imitation 的训练脚本
- 想把仿真真值录包对齐的工具

---

## 16. 外部系统接入指南

这一节是最关键的。

---

### 16.1 接你自己的高层控制器

最推荐的方式：

- 你的节点输出 `geometry_msgs/msg/Twist`
- 发布到 `/cmd_vel`

这样你不需要自己处理：

- 四轮舵向分解
- 转向限速
- 轮速归一化
- 轮角翻转

最小示例：

```python
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


class DemoCmd(Node):
    def __init__(self):
        super().__init__("demo_cmd")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.timer = self.create_timer(0.1, self.tick)

    def tick(self):
        msg = Twist()
        msg.linear.x = 0.8
        msg.linear.y = 0.0
        msg.angular.z = 0.2
        self.pub.publish(msg)


rclpy.init()
node = DemoCmd()
rclpy.spin(node)
```

---

### 16.2 接你自己的可视化或调试界面

最简单的接法不是改代码，而是直接替换 RViz 配置：

```bash
MAP_SIM_RVIZ_CONFIG=/abs/path/to/your_config.rviz bash ./run_sim_local.sh
```

这样适合这些情况：

- 你想加自己的 Marker / Path / OccupancyGrid 显示
- 你想把 fixed frame 改成 `odom`
- 你想加入自己的相机、检测框、轨迹或调试 topic

如果你要把别的 GUI 工具挂进主链，推荐做法是：

1. 复制 `sim_launch_omni.py`
2. 在 launch 里增加你的 Node
3. 保留原有 `gzserver` / `gzclient` / `rviz2` / 控制器启动顺序

这样接入最干净，也最不容易和 shell 层环境变量打架。

---

### 16.3 接你自己的低层底盘控制器

如果你要做的是：

- 自己实现 swerve inverse kinematics
- 自己做轮级闭环
- 自己测某种底盘控制律

那你应该直接发：

- `/steering_position_controller/commands`
- `/wheel_velocity_controller/commands`

但记住：

- 请先移除或禁用 `cmd_vel_to_swerve`

否则你和默认桥接节点会冲突。

---

### 16.4 接 SLAM / 里程计 / 点云感知

最常见的接法：

- 点云：
  - `/livox/lidar`
  - 或 `/livox/lidar_PointCloud2`
- IMU：
  - 推荐 `/imu_fixed`
  - 如果你要自己处理原始 IMU，可直接订阅 `/livox/imu`

对于外部 SLAM 来说，这个 bare 版的角色是：

- 只提供仿真输入
- 不再自带 SLAM 本体

也就是说，你的算法接入点就是这些 topic。

---

### 16.5 接需要真值位姿的算法

如果你需要：

- world pose
- odom
- TF

先开：

```bash
MAP_SIM_ENABLE_TF_PUB=1 bash ./run_sim_local.sh
```

然后消费：

- `/cube_robot/world_pose`
- `/livox/world_pose`
- `/nav_odom`
- `/odom`
- `odom -> base_footprint`

这对：

- 评估
- 监督学习
- 对比真值

都很方便。

---

### 16.6 接你自己的相机算法

当前建议分两种理解。

#### A. 你只是想保留接口约束

那你可以直接按照以下 topic 名接设计：

- `/livox/depth/image_raw`
- `/livox/depth/camera_info`
- `/livox/depth/depth/image_raw`
- `/livox/depth/depth/camera_info`
- `/livox/depth/points`

#### B. 你要真的在当前环境里启用 Gazebo 深度相机

当前必须显式放开：

```bash
MAP_SIM_ALLOW_UNSTABLE_DEPTH_CAMERA=1 bash ./run_sim_local_camera.sh
```

但这条路径不保证稳定。

所以如果你只是要给别的系统预留接口，当前更推荐：

- 把 topic 名和 frame 名先按这里定下来
- 未来换更稳的相机实现时，尽量不改接口名字

---

### 16.7 接你自己的世界 / 模型

有两种常见接法。

#### A. 自定义世界文件

直接传绝对路径：

```bash
MAP_SIM_WORLD=/abs/path/to/your.world bash ./run_sim_local.sh
```

#### B. 额外模型目录

通过环境变量把模型目录加进 Gazebo 搜索路径：

```bash
MAP_SIM_EXTRA_MODEL_PATHS=/abs/path/to/models bash ./run_sim_local.sh
```

Launch 层会把它拼进 `GAZEBO_MODEL_PATH`。

---

### 16.8 接运行时动态实体

如果你要在仿真跑起来之后再加东西：

- 相机
- 特定工具模型
- 目标物体

可以直接走 Gazebo 的 ROS service：

- `/spawn_entity`
- `/delete_entity`
- `/get_model_list`

`runtime_depth_camera.py` 就是一个现成例子：

- 先检查 Gazebo service 是否就绪
- 检查目标模型是否存在
- 生成 SDF
- 调用 `/spawn_entity`

如果你要动态挂自己的 Gazebo 模型，可以直接模仿它。

---

## 17. 关键内部接口清单

如果你只想快速知道“该接哪里”，看这张表就够了。

| 层级 | 接口 | 类型 | 是否推荐直接给外部用 | 说明 |
| --- | --- | --- | --- | --- |
| 高层控制 | `/cmd_vel` | `geometry_msgs/msg/Twist` | 是 | 最推荐 |
| 低层控制 | `/steering_position_controller/commands` | `std_msgs/msg/Float64MultiArray` | 高级用法 | 需要禁用桥接节点 |
| 低层控制 | `/wheel_velocity_controller/commands` | `std_msgs/msg/Float64MultiArray` | 高级用法 | 需要禁用桥接节点 |
| 雷达 | `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | 是 | Livox 风格 |
| 雷达 | `/livox/lidar_PointCloud2` | `sensor_msgs/msg/PointCloud2` | 是 | 标准点云 |
| IMU | `/livox/imu` | `sensor_msgs/msg/Imu` | 可以 | 原始接口 |
| IMU | `/imu_fixed` | `sensor_msgs/msg/Imu` | 是 | 推荐外部消费 |
| 真值位姿 | `/cube_robot/world_pose` | `geometry_msgs/msg/PoseStamped` | 可选 | 需启用 `tf_pub` |
| 雷达真值位姿 | `/livox/world_pose` | `geometry_msgs/msg/PoseStamped` | 可选 | 需启用 `tf_pub` |
| 平面里程计 | `/nav_odom` | `nav_msgs/msg/Odometry` | 可选 | 需启用 `tf_pub` |
| 兼容里程计 | `/odom` | `nav_msgs/msg/Odometry` | 可选 | 需启用 `tf_pub` |
| 深度图像 | `/livox/depth/*` | 相机相关消息 | 预留 | 当前默认不稳定 |

---

## 18. 你应该改哪些文件来接别的东西

### 18.1 只改运行参数，不改代码

改这些环境变量：

- `MAP_SIM_GZCLIENT`
- `MAP_SIM_WORLD`
- `MAP_SIM_SPAWN_X`
- `MAP_SIM_SPAWN_Y`
- `MAP_SIM_SPAWN_Z`
- `MAP_SIM_ENABLE_LIVOX`
- `MAP_SIM_ENABLE_IMU`
- `MAP_SIM_ENABLE_TF_PUB`
- `MAP_SIM_LIGHTING_PRESET`
- `MAP_SIM_LIGHTING_BRIGHTNESS`
- `MAP_SIM_SOLAR_TIME`

### 18.2 改仿真编排逻辑

改：

- `ws/src/ros2_livox_simulation/launch/sim_launch_omni.py`

适合做：

- 增删运行节点
- 替换控制桥
- 替换 IMU 后处理
- 改启动顺序

### 18.3 改机器人结构或传感器位置

改：

- `ws/src/ros2_livox_simulation/urdf/robot_sim_omni.xacro`

适合做：

- 改底盘尺寸
- 改轮距轴距
- 改 Livox / IMU / 相机挂点
- 增加新传感器 link / joint

### 18.4 改控制器接口

改：

- `ws/src/ros2_livox_simulation/config/cube_rob_omni_ctrl.yaml`

适合做：

- 改控制器种类
- 改关节组
- 改 interface 类型

### 18.5 改 `/cmd_vel` 到舵轮的控制逻辑

改：

- `ws/src/ros2_livox_simulation/scripts/cmd_vel_to_swerve.py`

适合做：

- 改 swerve 分解
- 改限速策略
- 改角度翻转策略
- 改对齐减速逻辑

### 18.6 改 IMU 对外行为

改：

- `ws/src/ros2_livox_simulation/src/fix_imu_time.cpp`

适合做：

- 时间偏移
- 姿态旋转
- 坐标系重映射

### 18.7 改真值位姿 / odom / TF

改：

- `ws/src/ros2_livox_simulation/src/tf_pub.cpp`

适合做：

- 改 odom frame 逻辑
- 改输出 topic
- 改 Livox yaw follow 逻辑

---

## 19. 常用命令

### 19.1 构建

```bash
bash ./build_local.sh
```

### 19.2 启动推荐 bare 主链（Gazebo GUI + RViz）

```bash
bash ./run_sim_local.sh
```

### 19.3 显式启动 GUI 快捷入口

```bash
bash ./run_sim_local_gui.sh
```

### 19.4 启动 headless

```bash
MAP_SIM_GZCLIENT=0 bash ./run_sim_local.sh
```

### 19.5 只开 Gazebo，不开 RViz

```bash
MAP_SIM_ENABLE_RVIZ=0 bash ./run_sim_local.sh
```

### 19.6 选择 cave 场景

```bash
bash ./run_sim_local.sh cave
```

### 19.7 启用 TF / odom 输出

```bash
MAP_SIM_ENABLE_TF_PUB=1 bash ./run_sim_local.sh
```

### 19.8 使用自定义 RViz 配置

```bash
MAP_SIM_RVIZ_CONFIG=/abs/path/to/your_config.rviz bash ./run_sim_local.sh
```

### 19.9 清理仿真残留

```bash
bash ./runlocal/stop.sh
```

### 19.10 查看深度相机运行时状态

```bash
bash ./open_depth_camera.sh --status
```

---

## 20. 已知限制

### 20.1 深度相机默认不可用

原因不是接口没写，而是：

- 当前 Gazebo Classic 环境里
- 一旦真正启用深度相机输出
- `gzserver` / `gzclient` 可能会因为 OGRE 断言退出

所以当前 bare 版策略是：

- 保留深度相机接口定义
- 保留相机挂点
- 保留运行时相机工具
- 默认不让它进入稳定主链

### 20.2 `tf_pub` 默认关闭

原因不是它不能用，而是：

- bare 版默认尽量少起不必要桥接
- 让你自己决定是否需要真值 pose / odom / TF

### 20.3 classic 分支保留但不是主路线

`classic` / `legacy` 分支仍在，但当前副本的主要验证和推荐使用路径是：

- `omni`

---

## 21. 对接别的系统时的推荐原则

如果你只记 6 条，请记下面这 6 条：

1. 高层控制优先发 `/cmd_vel`，不要一开始就碰底层舵轮控制器。
2. 做 SLAM / 感知时优先订阅 `/livox/lidar_PointCloud2` 和 `/imu_fixed`。
3. 需要真值位姿时再开 `MAP_SIM_ENABLE_TF_PUB=1`。
4. 要改默认可视化，优先换 `MAP_SIM_RVIZ_CONFIG`，再考虑改 launch。
5. 要做机器人结构或传感器布局改动，优先改 `robot_sim_omni.xacro`。
6. 要替换整个控制逻辑，优先改 `sim_launch_omni.py` 和 `cmd_vel_to_swerve.py`，不要在外面和默认桥接节点抢同一控制器。

---

## 22. 当前验证结论

这个 bare 版当前已验证：

- `build_local.sh` 可完成构建
- `run_sim_local.sh` 可拉起 bare 主链
- 车体和环境能正常运行
- `run_sim_local.sh` 当前默认可拉起 Gazebo GUI + RViz
- `run_sim_local_gui.sh` 可显式拉起 Gazebo GUI + RViz
- `gzclient` 可正常启动
- `rviz2` 可正常启动
- `map_sim_rviz` 节点可进入 ROS graph
- `/livox/lidar` 正常
- `/livox/lidar_PointCloud2` 正常
- `/livox/imu` 正常
- `/imu_fixed` 正常
- `/joint_states` 正常
- `/dynamic_joint_states` 正常
- omni 控制器可成功进入 active
- `/cmd_vel` 可被内部桥接成非零的转向和轮速控制命令

当前未作为稳定主链开放：

- `/livox/depth/*`

---

## 23. 一句话总结

这份 `NEXUS_GAZEBO_SIM` 现在最适合被当成：

> 一个保留车、环境、Gazebo GUI、RViz、控制桥和传感器接口的 Gazebo 仿真底座。

如果你要接自己的：

- 控制器
- 规划器
- SLAM
- 感知
- 数据采集脚本

优先从这些接口入手：

- 控制输入：`/cmd_vel`
- 点云输入：`/livox/lidar` 或 `/livox/lidar_PointCloud2`
- IMU 输入：`/imu_fixed`
- 真值位姿：开启 `MAP_SIM_ENABLE_TF_PUB=1` 后读取 `/cube_robot/world_pose` / `/nav_odom`

这样接入成本最低，也最不容易和内部实现打架。

# NEXUS_GAZEBO_SIM 重构完成报告

**重构日期**: 2026-07-02  
**修复日期**: 2026-07-03  
**执行方案**: 从"嵌套式 ws/" 到标准 ROS 2 工作区  
**状态**: ✅ **重构完成 + 修复验证通过**

---

## 重构前后对比

### 目录结构变化

**重构前**:
```
NEXUS_GAZEBO_SIM/
├── ws/                    ← 嵌套工作区
│   ├── src/               ← ROS2 包混在一起
│   ├── build/, install/   ← 重复构建产物
├── 18个 .sh 脚本散落根目录
└── 死代码混在包内
```

**重构后**:
```
NEXUS_GAZEBO_SIM/          ← 标准 ROS 2 工作区根目录
├── src/                   ← 所有 ROS 2 包（扁平）
│   ├── ros2_livox_simulation/
│   ├── livox_ros_driver2/
│   ├── nexus_fastlio/
│   ├── nexus_gp_mapping/
│   ├── nexus_elevation_mppi/
│   ├── nexus_teleop/
│   └── third_party/
├── scripts/               ← 所有运维脚本
├── config/                ← 全局配置
├── launch/                ← 跨包编排
├── tools/                 ← 非 ROS 工具
├── docs/                  ← 文档
└── archive/               ← 死代码隔离
```

---

## ✅ 已完成的工作

### Step 1: 目录骨架创建 ✅
### Step 2: 工作区扁平化 ✅
### Step 4: 核心包拆分 ✅
- 从 `ros2_livox_simulation` 拆分出 4 个新算法包
- 每个包包含 `package.xml` + `CMakeLists.txt` + `scripts/`

### Step 5: 第三方包归口 ✅
- 14 个第三方包移到 `src/third_party/`

### Step 6: 根目录脚本归类 ✅
- 20 个脚本移到 `scripts/`

---

## 🔧 2026-07-03 修复清单

重构后发现并修复的 5 个致命问题 + 1 个 UI 问题：

### 1. livox build.sh 清空炸弹 ✅

**问题**: `src/livox_ros_driver2/build.sh` 第 30-32 行 `rm -rf ../../install/` 会清空整个工作区 install 目录。

**修复**: 改为只清理 livox 自己的 build 残留：
```bash
rm -rf ../../build/livox_ros_driver2
rm -rf ../../install/livox_ros_driver2
```

### 2. 4 个新包 CMakeLists 漏 RENAME ✅

**问题**: `nexus_fastlio`、`nexus_teleop`、`nexus_gp_mapping`、`nexus_elevation_mppi` 的 `install(PROGRAMS ...)` 没有 `RENAME`，导致安装的文件名带 `.py` 后缀，`ros2 run` 和 launch 的 `executable=` 找不到。

**修复**: 每个 `.py` 脚本单独 `install(PROGRAMS)` + `RENAME` 去掉 `.py` 后缀。

### 3. ~/.local/bin/cmake 坏 wrapper ✅

**问题**: pip 安装的 cmake wrapper 无法运行（`ModuleNotFoundError: No module named 'cmake'`），shadow 了系统 `/usr/bin/cmake`。

**修复**: `mv ~/.local/bin/cmake ~/.local/bin/cmake.broken`

### 4. setuptools 79.0.1 不兼容 ✅

**问题**: `~/.local` 里的 setuptools 79.0.1 移除了 `pkgutil.ImpImporter`，破坏 ROS Humble 的 `rosidl_generate_interfaces`。

**修复**: 构建时 `export PYTHONNOUSERSITE=1` 用系统 setuptools 59.6.0。运行时**不设**此变量（`elevation_mapping_cupy` 依赖 `~/.local` 里的 `simple_parsing`）。

### 5. 17 个脚本 ROOT_DIR 指向错误 ✅

**问题**: `scripts/*.sh` 里 `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` 指向 `scripts/` 而非项目根，导致找不到 `install/setup.bash`。

**修复**: 统一改为 `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`。

### 6. gzclient 在 llvmpipe 软件渲染下崩溃 ✅

**问题**: OGRE `AxisAlignedBox::setExtents` 断言失败（`min > max`），gzclient 启动 7 秒后崩溃。

**根因**: 软件渲染下 OGRE 阴影系统 bounding box 计算异常。

**修复**: `_world_lighting.py` 加 `disable_shadows` 参数，`sim_launch_omni.py` 检测到 `MAP_SIM_SOFTWARE_GL_DETECTED=1` 时自动设 `<shadows>false</shadows>`。

---

## 构建验证

所有 6 个主包成功构建：

| 包 | 状态 |
|---|---|
| livox_ros_driver2 | ✅ |
| ros2_livox_simulation | ✅ |
| nexus_fastlio | ✅ |
| nexus_teleop | ✅ |
| nexus_gp_mapping | ✅ |
| nexus_elevation_mppi | ✅ |

当前主线可执行文件全部正确安装（含 RENAME）。

---

## 运行验证

### Bare 仿真 (headless)

| 接口 | 频率 | 状态 |
|---|---|---|
| /livox/lidar_PointCloud2 | 13 Hz | ✅ |
| /livox/imu | 133 Hz | ✅ |
| /joint_states | 66 Hz | ✅ |
| 3 控制器 | active | ✅ |
| /cmd_vel → 4舵轮+4轮速 | 非零 | ✅ |

### CuPy 高程图 + 通行性地图 (headless)

| 接口 | 频率 | 状态 |
|---|---|---|
| /elevation_mapping_node/elevation_map | 3-5 Hz | ✅ |
| /traversability_map | 3-8 Hz | ✅ |
| /cloud_registered, /cloud_body | 正常 | ✅ |

### 完整 MPPI 导航栈 (headless)

| 接口 | 频率 | 状态 |
|---|---|---|
| /mppi/optimal_path | 12 Hz | ✅ |
| /cmd_vel | 12 Hz | ✅ |
| MPPI tracking goal | 响应 | ✅ |

### 完整 UI (gzclient + RViz + CuPy + MPPI)

| 组件 | 状态 |
|---|---|
| gzserver | ✅ 运行中 |
| gzclient | ✅ 运行中（阴影修复后不崩溃） |
| rviz2 | ✅ 运行中 |
| CuPy 高程图 | ✅ |
| traversability_to_map | ✅ |
| mppi_navigator | ✅ |
| 所有 topic | ✅ 正常发布 |

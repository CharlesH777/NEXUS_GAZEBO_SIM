# 贡献指南

感谢你对 NEXUS Gazebo Sim 项目的兴趣！请阅读以下指南后再提交贡献。

## 1. 许可证

本项目采用 **专有授权（All Rights Reserved）**。版权所有 © 2026 Charles。

提交的代码将被视为作者的专有成果，其知识产权归作者所有。提交 PR 即表示你同意将贡献的知识产权转让给作者。

第三方代码必须保持其原始许可证不变，并在 `NOTICE.md` 中声明来源。

## 2. 开发环境

- **OS**: Ubuntu 22.04
- **ROS 2**: Humble
- **Gazebo**: Classic 11
- **Python**: 3.10
- **构建系统**: colcon

```bash
# 克隆并构建
git clone <repo-url>
cd NEXUS_GAZEBO_SIM
bash scripts/build.sh
```

## 3. 代码规范

### Bash 脚本

- 使用 `#!/usr/bin/env bash`，不用 `#!/bin/bash`
- 开头加 `set -euo pipefail`（监控类脚本除外，可按需放宽）
- 路径用 `$ROOT_DIR` 动态解析，**禁止硬编码 `/home/用户名/...`**
- 用 `$ROOT_DIR` 模式：`ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`
- 外部工作区路径必须支持环境变量覆盖：`${VAR:-$ROOT_DIR/...}`

### Python

- 遵循 PEP 8
- ROS 2 节点用 `rclpy`，不依赖 `rospy`
- 路径用 `os.path` 或 `pathlib` 动态解析，**禁止硬编码绝对路径**

### C++

- 遵循 ROS 2 编码规范
- CMakeLists.txt 中不要写入机器特定的路径

### ROS 2 包

- `package.xml` 必须声明 `<license>All Rights Reserved</license>`
- `package.xml` 的 `<maintainer>` 邮箱必须有效
- 新增依赖必须在 `package.xml` 和 `CMakeLists.txt` 中同步声明

## 4. 提交规范

### Commit Message

```
<类型>: <简述>

<详细说明>
```

类型：
- `feat`: 新功能
- `fix`: 修复 bug
- `refactor`: 重构
- `docs`: 文档
- `build`: 构建系统
- `ci`: CI 配置
- `chore`: 杂项

### PR 流程

1. 从 `main` 拉分支：`git checkout -b feat/your-feature`
2. 确保 `bash scripts/build.sh` 通过
3. 确保仿真能启动：`bash scripts/start.sh`
4. 提交 PR，描述改动内容和测试方法

### PR 检查清单

- [ ] 代码不包含硬编码的绝对路径
- [ ] `package.xml` license 标签正确
- [ ] 新增脚本有 `ROOT_DIR` 动态解析
- [ ] `bash scripts/build.sh` 成功
- [ ] 没有提交 `build/` `install/` `log/` 目录
- [ ] 没有 `console.log` / `print` 调试残留

## 5. 第三方代码

引入第三方代码时：
1. 放在 `src/third_party/` 下
2. 保留原始 LICENSE 文件
3. 在 `NOTICE.md` 中声明来源和许可证
4. 确认许可证与专有授权兼容（MIT、BSD、Apache-2.0 可作为第三方库引入，但不影响本项目整体授权）

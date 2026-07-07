# 说明

主文档已经迁到 `README.md`。

如果你是从旧目录或旧压缩包里点进来的，直接看仓库根目录的 `README.md` 就行。

补充：这轮已经把地图资料入口也并到仓库里了，优先看下面两个文件：

- `MAPS.md`：已经集成进工程、可以直接启动的地图清单
- `MAP_SOURCES.md`：已集成地图的来源说明 + 后续可继续扩展的候选地图

常用启动例子：

```bash
MAP_SIM_GZCLIENT=0 \
MAP_SIM_SPAWN_ROBOT=0 \
MAP_SIM_WORLD=marsyard2021_map_only.world \
bash ./run_sim_local.sh
```

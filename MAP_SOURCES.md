# Map source index and collection notes

This file records where the currently integrated map assets came from, plus a shortlist of additional terrain sources worth evaluating later.

The goal is traceability, not legal advice. If you plan to redistribute the project, re-check upstream licenses and attribution requirements.

## Integrated maps: source table

### 1) rm_2026
- Local model:
  - `ws/src/ros2_livox_simulation/models/rm_2026`
- Status:
  - original in-project map, not imported during this collection round
- Notes:
  - keep as the default baseline world for existing Livox simulation work

### 2) apollo15_landing_site_1000x1000
- Local model:
  - `ws/src/ros2_livox_simulation/models/apollo15_landing_site_1000x1000`
- Main upstream reference used during collection:
  - `https://raw.githubusercontent.com/MobileRobots/amr-ros-config/master/gazebo/moon.world`
- Upstream family / provenance:
  - MobileRobots / AMR ROS config lunar terrain assets
- Local adaptation done here:
  - wrapped as a standalone local Gazebo Classic model
  - added local `model.config` and `model.sdf`
  - kept the terrain self-contained under this project
- Notes:
  - this is the cleanest lunar heightmap-style map currently imported into the repo

### 3) marsyard2020_terrain
- Local model:
  - `ws/src/ros2_livox_simulation/models/marsyard2020_terrain`
- Upstream repo family:
  - `https://github.com/LeoRover/leo_simulator-ros2`
- Upstream world reference checked during collection:
  - `https://raw.githubusercontent.com/LeoRover/leo_simulator-ros2/ros2/leo_gz_worlds/worlds/marsyard2020.sdf`
- Expected upstream asset family:
  - `leo_gz_worlds/models/marsyard2020_terrain/...`
- Local adaptation done here:
  - wrapped into a Classic-friendly local model with local `model.config` / `model.sdf`
- Notes:
  - useful when you want a compact Mars-style terrain without extra heightmap conversion steps

### 4) marsyard2021_terrain
- Local model:
  - `ws/src/ros2_livox_simulation/models/marsyard2021_terrain`
- Upstream repo family:
  - `https://github.com/LeoRover/leo_simulator-ros2`
- Upstream world reference checked during collection:
  - `https://raw.githubusercontent.com/LeoRover/leo_simulator-ros2/ros2/leo_gz_worlds/worlds/marsyard2021.sdf`
- Expected upstream asset family:
  - `leo_gz_worlds/models/marsyard2021_terrain/...`
- Local adaptation done here:
  - original heightmap source kept as `marsyard_terrain_hm.tif`
  - converted to local `marsyard_terrain_hm.png` for Gazebo Classic compatibility
  - replaced heavy texture dependency with a small local placeholder texture so the map stays self-contained
  - wrapped obstacle meshes into the local model
- Notes:
  - probably the most practical imported Mars map for compact SLAM / local navigation testing

### 5) marsyard2022_terrain
- Local model:
  - `ws/src/ros2_livox_simulation/models/marsyard2022_terrain`
- Upstream repo family:
  - `https://github.com/LeoRover/leo_simulator-ros2`
- Upstream world reference checked during collection:
  - `https://raw.githubusercontent.com/LeoRover/leo_simulator-ros2/ros2/leo_gz_worlds/worlds/marsyard2022.sdf`
- Expected upstream asset family:
  - `leo_gz_worlds/models/marsyard2022_terrain/...`
- Local adaptation done here:
  - original heightmap source kept as `marsyard2022_terrain_hm.tif`
  - converted to local `marsyard2022_terrain_hm.png` for Gazebo Classic compatibility
  - replaced heavy texture dependency with a small local placeholder texture
- Notes:
  - nice second Marsyard variant when you want a different local relief pattern from 2021

### 6) mars_gazebo_topography
- Local model:
  - `ws/src/ros2_livox_simulation/models/mars_gazebo_topography`
- Upstream repo family:
  - `https://github.com/aunefyren/mars_gazebo`
- Direct file reference confirmed during collection:
  - `https://raw.githubusercontent.com/aunefyren/mars_gazebo/master/worlds/model_texture.jpg`
- Related upstream asset family:
  - `mars_topografi.dae` plus its texture from the same repo family
- Local adaptation done here:
  - wrapped the mesh into a local Gazebo model
  - added local `model.config` / `model.sdf`
  - downloaded the required JPG texture locally so runtime does not depend on the network
- Notes:
  - best choice here when you want a larger Mars-like surface rather than a compact yard

## Current integrated world files

Under `ws/src/ros2_livox_simulation/world/`:

- `rm_2026_slam_world.world`
- `apollo15_map_only.world`
- `marsyard2020_map_only.world`
- `marsyard2021_map_only.world`
- `marsyard2022_map_only.world`
- `mars_gazebo_topography_map_only.world`
- `space_maps_showcase.world`

## Additional candidate map sources worth evaluating later

These were identified during the search phase but are not yet fully imported into this repository.

### A) space_robotics_gz_envs
- Repo:
  - `https://github.com/AndrejOrsula/space_robotics_gz_envs`
- Relevant files checked:
  - `https://raw.githubusercontent.com/AndrejOrsula/space_robotics_gz_envs/main/worlds/moon.sdf`
  - `https://raw.githubusercontent.com/AndrejOrsula/space_robotics_gz_envs/main/worlds/mars.sdf`
- Why it matters:
  - has ready-made Moon / Mars environments for newer Gazebo Sim
- Why it is not fully imported yet:
  - upstream targets newer `gz sim` workflows and references a larger model family
  - would need a more deliberate Gazebo Classic compatibility pass
- Recommendation:
  - strong candidate if you later decide to keep a parallel Gazebo Sim branch

### B) Leo Rover `leo_gz_worlds`
- Index reference checked:
  - `https://index.ros.org/p/leo_gz_worlds/`
- Why it matters:
  - likely the best compact Mars-yard source family for ROS-adjacent usage
- Status:
  - partially imported already through 2020 / 2021 / 2022 map assets
- Recommendation:
  - if you want more from the same family, keep mining this repo first

### C) MobileRobots lunar world family
- Main article / background references checked during search:
  - `https://www.osrfoundation.org/gazebo-renders-the-moon/`
- Why it matters:
  - practical lunar world material with ROS/Gazebo lineage
- Status:
  - partially reflected here through the Apollo-style landing-site model

### D) cagrikilic / simulation-environment
- Repo checked:
  - `https://github.com/cagrikilic/simulation-environment`
- Why it matters:
  - broader planetary simulation environment references
- Status:
  - examined as a candidate, not imported in this round
- Recommendation:
  - lower priority than Leo Rover assets if your current focus is local ROS 2 + Classic compatibility

## Practical recommendation for this repo

If the target remains:
- ROS 2 Humble
- Gazebo Classic 11
- local self-contained assets

then the best immediate map set is already:
- `apollo15_landing_site_1000x1000`
- `marsyard2020_terrain`
- `marsyard2021_terrain`
- `marsyard2022_terrain`
- `mars_gazebo_topography`

If you want the next expansion round, the sensible order is:
1. import one more compact lunar heightmap
2. extract more Marsyard-family terrain variants first
3. only then consider deeper `gz sim`-native planetary environments

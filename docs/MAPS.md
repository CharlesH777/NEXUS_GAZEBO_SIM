# Maps integrated into this ROS 2 / Gazebo Classic project

This project now carries a small local catalog of terrain/map assets under:

- `ws/src/ros2_livox_simulation/models/`
- `ws/src/ros2_livox_simulation/world/`

Goal:
- keep everything local to the project
- avoid depending on external model downloads at runtime
- stay compatible with ROS 2 Humble + Gazebo Classic 11

## Included maps

1. `rm_2026`
- Type: custom RM map mesh
- Model dir:
  - `models/rm_2026`
- World:
  - `world/rm_2026_slam_world.world`
- Notes:
  - original in-project map
  - still the default world

2. `apollo15_landing_site_1000x1000`
- Type: lunar heightmap
- Model dir:
  - `models/apollo15_landing_site_1000x1000`
- World:
  - `world/apollo15_map_only.world`
- Notes:
  - wrapped as a local Gazebo Classic heightmap model
  - uses local heightmap + local diffuse texture

3. `marsyard2020_terrain`
- Type: Mars-style terrain mesh
- Model dir:
  - `models/marsyard2020_terrain`
- World:
  - `world/marsyard2020_map_only.world`
- Notes:
  - mesh-based terrain
  - simplest Mars terrain to drop into Classic

4. `marsyard2021_terrain`
- Type: Mars-style heightmap + obstacle meshes
- Model dir:
  - `models/marsyard2021_terrain`
- World:
  - `world/marsyard2021_map_only.world`
- Notes:
  - original heightmap source was TIF
  - converted locally to PNG for Gazebo Classic compatibility
  - includes `lava.obj`, `rocks_big.obj`, `rocks_medium.obj`
  - texture replaced with a lightweight local placeholder to keep the package usable

5. `marsyard2022_terrain`
- Type: Mars-style heightmap
- Model dir:
  - `models/marsyard2022_terrain`
- World:
  - `world/marsyard2022_map_only.world`
- Notes:
  - original heightmap source was TIF
  - converted locally to PNG for Gazebo Classic compatibility
  - texture replaced with a lightweight local placeholder

6. `mars_gazebo_topography`
- Type: large Mars topography mesh
- Model dir:
  - `models/mars_gazebo_topography`
- World:
  - `world/mars_gazebo_topography_map_only.world`
- Notes:
  - mesh + local JPG texture
  - useful when you want a large planetary-style surface instead of a compact yard

7. `space_maps_showcase`
- Type: convenience showcase world
- World:
  - `world/space_maps_showcase.world`
- Notes:
  - places several imported maps far apart in one world for quick visual inspection
  - better for browsing than for precise experiments

## How to run a specific map

Default world:

```bash
bash ./run_sim_local.sh
```

Headless map-only launch:

```bash
MAP_SIM_GZCLIENT=0 \
MAP_SIM_SPAWN_ROBOT=0 \
MAP_SIM_WORLD=marsyard2021_map_only.world \
bash ./run_sim_local.sh
```

Map + robot:

```bash
MAP_SIM_WORLD=marsyard2022_map_only.world \
MAP_SIM_SPAWN_ROBOT=1 \
MAP_SIM_SPAWN_Z=1.0 \
bash ./run_sim_local.sh
```

Apollo 15 terrain only:

```bash
MAP_SIM_GZCLIENT=0 \
MAP_SIM_SPAWN_ROBOT=0 \
MAP_SIM_WORLD=apollo15_map_only.world \
bash ./run_sim_local.sh
```

Browse all imported maps:

```bash
MAP_SIM_WORLD=space_maps_showcase.world \
MAP_SIM_SPAWN_ROBOT=0 \
bash ./run_sim_local.sh
```

## Source / provenance notes

These map assets were collected from public upstream material and then adapted for local use inside this project.

Main references used during collection:

- MobileRobots / AMR ROS config
  - Apollo 15 lunar terrain world / texture references
- Leo Rover / Marsyard terrain assets
  - `marsyard2020`, `marsyard2021`, `marsyard2022`
- `mars_gazebo`
  - large Mars topography mesh + texture

## Compatibility notes

This repo is using:
- ROS 2 Humble
- Gazebo Classic 11

So a few upstream assets needed adaptation:

- some upstream worlds were written for newer `gz sim` flows rather than Gazebo Classic
- some heightmaps were provided as `.tif`, but Classic is happier with `.png`
- some huge upstream textures were swapped for tiny local placeholders so the map remains usable without dragging giant files around

That means these assets are integrated for practical local simulation, not preserved as perfect upstream mirrors.

## Suggested next additions

If you want me to keep expanding this catalog later, the next sensible direction is:

1. more lunar heightmaps
2. more compact Mars yard maps suitable for SLAM / navigation
3. rough outdoor quarry / desert maps that behave like planetary analog terrain
4. a `maps/README_sources.md` table with exact upstream URLs for every imported file

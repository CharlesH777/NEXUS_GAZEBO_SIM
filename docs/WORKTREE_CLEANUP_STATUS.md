# NEXUS_GAZEBO_SIM Worktree Cleanup Status

**Date**: 2026-07-06
**Scope**: workspace slimming, historical build cleanup, git noise reduction, Pointcept/semantic-segmentation removal

## Cleaned In This Pass

- Removed historical workspace artifacts:
  - `build/`
  - `install/`
  - `log/`
  - `output/`
  - `archive/`
- Extended `.gitignore` so historical and runtime outputs stay out of `git`:
  - ignore `/archive/`
  - ignore `/output/`
- Removed confirmed-unused cave/cache content:
  - `.external_worlds/darpa_subt_worlds/.git`
  - `.fuel_models/*__scaled_0p2`
  - `.fuel_models/*__scaled_0p2__scaled_0p3`
- Removed the point-cloud semantic-segmentation stack:
  - `scripts/run_street_infer.sh`
  - `scripts/utils/street_infer.sh`
  - `src/nexus_semantics/`
  - `tools/Pointcept/`

## Approximate Space Reclaimed

- Removed about `5.8G` of local historical data:
  - `archive/` about `5.4G`
  - `build/` about `366M`
  - `log/` about `30M`
  - `install/` about `7.6M`
  - `output/` about `2.8M`
- Removed about `1.7G` of confirmed-unused local assets:
  - `darpa_subt_worlds/.git` about `263M`
  - cave `__scaled_0p2*` model variants about `1.4G`
- Removed about `12G` of Pointcept semantic-segmentation assets:
  - `tools/Pointcept/.conda-env` about `11G`
  - weights, code, and bundled runtime assets about `1G`

## Intentionally Kept

- `src/`
  Reason: active ROS 2 packages.
- `config/`, `launch/`, `scripts/`, `runlocal/`, `docs/`
  Reason: current bringup and documentation layer.
- `tools/elevation_ros2/`
  Reason: current helper scripts for the external elevation workspace.
- `.fuel_models/`, `.external_worlds/`
  Reason: large local simulation assets/caches; kept to avoid breaking cave/world variants in this pass.

## Current Heavy Directories Still Present

- workspace total about `2.5G`
- `.fuel_models/` about `1.4G`
- `.external_worlds/` about `638M`
- `src/` about `337M`
- `tools/` about `44K`

## Remaining Structural Debt

- The repository is still in the middle of a path migration:
  - old tracked paths under `ws/src/...`
  - current active paths under `src/...`
- Some documents still reference `ws/src/...` and old root-level scripts.
- Root-level bringup is still not packaged as a dedicated ROS 2 `*_bringup` package.

## Next Recommended Cleanup

1. Finish the `ws/src` -> `src` git migration.
2. Update docs and helper scripts that still reference old paths.
3. Package root-level launch/config/scripts into a bringup package.
4. Decide whether `.fuel_models/` and `.external_worlds/` should remain local-only or move to an external setup step.

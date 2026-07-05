#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export MAP_SIM_BASE_VARIANT=omni
exec "$ROOT_DIR/scripts/run_sim.sh" "$@"

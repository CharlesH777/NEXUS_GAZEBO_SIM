#!/usr/bin/env bash

map_sim_is_truthy() {
  case "${1,,}" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

map_sim_detect_nvidia_gl_renderer() {
  if ! command -v glxinfo >/dev/null 2>&1; then
    return 1
  fi

  local glxinfo_output=""
  if command -v timeout >/dev/null 2>&1; then
    glxinfo_output="$(
      env \
        __NV_PRIME_RENDER_OFFLOAD=1 \
        __GLX_VENDOR_LIBRARY_NAME=nvidia \
        LIBGL_ALWAYS_SOFTWARE=0 \
        timeout 3s glxinfo -B 2>/dev/null || true
    )"
  else
    glxinfo_output="$(
      env \
        __NV_PRIME_RENDER_OFFLOAD=1 \
        __GLX_VENDOR_LIBRARY_NAME=nvidia \
        LIBGL_ALWAYS_SOFTWARE=0 \
        glxinfo -B 2>/dev/null || true
    )"
  fi

  if [ -z "$glxinfo_output" ]; then
    return 1
  fi

  if ! printf '%s\n' "$glxinfo_output" | grep -q 'OpenGL vendor string: NVIDIA Corporation'; then
    return 1
  fi

  export MAP_SIM_NVIDIA_GL_RENDERER="$(
    printf '%s\n' "$glxinfo_output" \
      | awk -F': ' '/OpenGL renderer string:/ {print $2; exit}'
  )"
  return 0
}

apply_map_sim_gpu_gl_defaults() {
  if [ "${MAP_SIM_GPU_GL_DEFAULTS_APPLIED:-0}" = "1" ]; then
    return 0
  fi
  export MAP_SIM_GPU_GL_DEFAULTS_APPLIED=1
  export MAP_SIM_NVIDIA_GL_ACTIVE=0
  export MAP_SIM_GL_BACKEND="${MAP_SIM_GL_BACKEND:-default}"

  if map_sim_is_truthy "${MAP_SIM_USE_SOFTWARE_GL:-0}"; then
    export MAP_SIM_GL_BACKEND="software-forced"
    return 0
  fi

  if ! map_sim_is_truthy "${MAP_SIM_PREFER_NVIDIA_GL:-1}"; then
    export MAP_SIM_GL_BACKEND="default"
    return 0
  fi

  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "[WARN] GPU project: nvidia-smi is unavailable; falling back to the default OpenGL path."
    return 0
  fi

  if ! map_sim_detect_nvidia_gl_renderer; then
    echo "[WARN] GPU project: NVIDIA OpenGL offload was not detected; falling back to the default OpenGL path."
    return 0
  fi

  unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER MESA_LOADER_DRIVER_OVERRIDE || true
  export __NV_PRIME_RENDER_OFFLOAD=1
  export __GLX_VENDOR_LIBRARY_NAME=nvidia
  export __VK_LAYER_NV_optimus=NVIDIA_only
  export MAP_SIM_USE_SOFTWARE_GL=0
  export MAP_SIM_NVIDIA_GL_ACTIVE=1
  export MAP_SIM_GL_BACKEND="nvidia-offload"
}

apply_map_sim_gpu_headless_defaults() {
  if [ "${MAP_SIM_ENABLE_HEADLESS_RENDERING_WAS_SET:-0}" = "1" ]; then
    return 0
  fi

  if [ "${MAP_SIM_NVIDIA_GL_ACTIVE:-0}" = "1" ] && [ "${MAP_SIM_GZCLIENT:-1}" != "1" ]; then
    export MAP_SIM_ENABLE_HEADLESS_RENDERING=1
    export MAP_SIM_GPU_HEADLESS_RENDERING_AUTO=1
  fi
}

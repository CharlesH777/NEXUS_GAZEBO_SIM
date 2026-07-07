#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET


IGNITION_URI = "https://gazebosim.org/schema"
ET.register_namespace("ignition", IGNITION_URI)


LIGHTING_PRESETS = {
    "world": {
        "ambient_scale": 1.0,
        "background_scale": 1.0,
        "sun_diffuse_scale": 1.0,
        "sun_specular_scale": 1.0,
    },
    "dim": {
        "ambient_scale": 0.65,
        "background_scale": 0.72,
        "sun_diffuse_scale": 0.82,
        "sun_specular_scale": 0.55,
    },
    "dark": {
        "ambient_scale": 0.42,
        "background_scale": 0.56,
        "sun_diffuse_scale": 0.64,
        "sun_specular_scale": 0.35,
    },
}


DEFAULT_SCENE_AMBIENT = (0.4, 0.4, 0.4, 1.0)
DEFAULT_SCENE_BACKGROUND = (0.7, 0.7, 0.7, 1.0)
DEFAULT_SUN_DIFFUSE = (0.8, 0.8, 0.8, 1.0)
DEFAULT_SUN_SPECULAR = (0.2, 0.2, 0.2, 1.0)
DEFAULT_SUN_DIRECTION = (-0.5, 0.1, -0.9)
NIGHT_AMBIENT = (0.035, 0.04, 0.06, 1.0)
NIGHT_BACKGROUND = (0.015, 0.02, 0.05, 1.0)
DAY_SUN_DIFFUSE = (1.0, 0.98, 0.94, 1.0)
WARM_SUN_DIFFUSE = (1.0, 0.72, 0.45, 1.0)
DAY_SUN_SPECULAR = (0.28, 0.28, 0.28, 1.0)
WARM_SUN_SPECULAR = (0.36, 0.25, 0.18, 1.0)
SOLAR_PLUGIN_NAME = "map_sim_solar_lighting"
SOLAR_PLUGIN_FILENAME = "libsolar_lighting_world_plugin.so"
SOLAR_TIME_TOPIC = "/map_sim/solar_time_hours"


def maybe_prepare_world_with_lighting(
    world_path: str,
    lighting_preset: str,
    brightness_scale: float,
    solar_time: str | None = None,
    disable_shadows: bool = False,
) -> str:
    preset_key = (lighting_preset or "dim").strip().lower()
    if preset_key not in LIGHTING_PRESETS:
        raise ValueError(
            f"Unsupported lighting preset '{lighting_preset}'. "
            f"Expected one of: {', '.join(sorted(LIGHTING_PRESETS))}"
        )

    brightness_scale = max(0.1, float(brightness_scale))
    solar_hours = _parse_solar_time_hours(solar_time)
    if (
        solar_hours is None
        and preset_key == "world"
        and abs(brightness_scale - 1.0) < 1e-6
        and not disable_shadows
    ):
        return world_path

    source_path = Path(world_path)
    tree = ET.parse(source_path)
    root = tree.getroot()
    world = root.find("world")
    if world is None:
        raise ValueError(f"World file does not contain a <world> element: {world_path}")

    preset = LIGHTING_PRESETS[preset_key]
    ambient_scale = preset["ambient_scale"] * brightness_scale
    background_scale = preset["background_scale"] * brightness_scale
    sun_diffuse_scale = preset["sun_diffuse_scale"] * brightness_scale
    sun_specular_scale = preset["sun_specular_scale"] * brightness_scale

    scene = world.find("scene")
    if scene is None:
        scene = ET.Element("scene")
        world.insert(0, scene)

    if disable_shadows:
        _set_scalar(scene, "shadows", "false")

    base_ambient = _parse_rgba(
        scene.findtext("ambient"),
        DEFAULT_SCENE_AMBIENT,
    )
    base_background = _parse_rgba(
        scene.findtext("background"),
        DEFAULT_SCENE_BACKGROUND,
    )
    scaled_ambient = _scale_rgba(base_ambient, ambient_scale)
    scaled_background = _scale_rgba(base_background, background_scale)

    if solar_hours is None:
        removed_sun_index = _remove_default_sun_include(world)
        sun_light = _find_or_create_sun_light(world, removed_sun_index)
        _set_rgba(scene, "ambient", scaled_ambient)
        _set_rgba(scene, "background", scaled_background)
        _configure_sun_light(
            sun_light,
            _scale_rgba(DEFAULT_SUN_DIFFUSE, sun_diffuse_scale),
            _scale_rgba(DEFAULT_SUN_SPECULAR, sun_specular_scale),
            DEFAULT_SUN_DIRECTION,
            True,
        )
        _remove_solar_plugin(world)
        safe_suffix = f"{preset_key}_{str(brightness_scale).replace('.', '_')}"
    else:
        solar = _compute_solar_state(solar_hours)
        final_ambient = _mix_rgba(
            NIGHT_AMBIENT,
            scaled_ambient,
            solar["ambient_blend"],
        )
        final_background = _mix_rgba(
            NIGHT_BACKGROUND,
            scaled_background,
            solar["background_blend"],
        )
        sun_diffuse = _scale_rgba(
            _mix_rgba(DAY_SUN_DIFFUSE, WARM_SUN_DIFFUSE, solar["warmth"]),
            sun_diffuse_scale * solar["sun_level"],
        )
        sun_specular = _scale_rgba(
            _mix_rgba(DAY_SUN_SPECULAR, WARM_SUN_SPECULAR, solar["warmth"]),
            sun_specular_scale * solar["sun_level"],
        )
        _set_rgba(scene, "ambient", final_ambient)
        _set_rgba(scene, "background", final_background)
        _remove_light_by_name(world, "map_sim_sun")
        _ensure_solar_plugin(world, solar_hours, light_name="sun")
        safe_suffix = (
            f"{preset_key}_{str(brightness_scale).replace('.', '_')}"
            f"__solar_{_format_time_token(solar_hours)}"
        )

    output_dir = Path(tempfile.gettempdir()) / "map_sim_world_lighting"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{source_path.stem}__lighting_{safe_suffix}.world"
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return str(output_path)


def _parse_solar_time_hours(text: str | None) -> float | None:
    if text is None:
        return None

    stripped = text.strip()
    if not stripped:
        return None

    if ":" in stripped:
        parts = stripped.split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"Unsupported solar time format: {text}")
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError(f"Solar time is out of range: {text}")
        value = hour + minute / 60.0 + second / 3600.0
    else:
        value = float(stripped)

    value = math.fmod(value, 24.0)
    if value < 0.0:
        value += 24.0
    return value


def _compute_solar_state(hours: float) -> dict[str, float | bool | tuple[float, float, float]]:
    hour_angle = (hours - 12.0) * math.pi / 12.0
    sun_east = -math.sin(hour_angle)
    sun_up = math.cos(hour_angle)
    above_horizon = max(0.0, sun_up)
    twilight = _clamp01((sun_up + 0.20) / 1.20)

    return {
        "direction": (-sun_east, 0.0, -sun_up),
        "ambient_blend": twilight ** 0.55,
        "background_blend": twilight ** 0.35,
        "sun_level": above_horizon ** 0.85,
        "warmth": _clamp01(1.0 - above_horizon * 2.5),
        "cast_shadows": above_horizon > 0.05,
    }


def _remove_default_sun_include(world: ET.Element) -> int | None:
    removed_sun_index = None
    for index, child in enumerate(list(world)):
        if child.tag != "include":
            continue
        uri = child.find("uri")
        if uri is not None and (uri.text or "").strip() == "model://sun":
            world.remove(child)
            if removed_sun_index is None:
                removed_sun_index = index
    return removed_sun_index


def _find_or_create_sun_light(world: ET.Element, insert_index: int | None) -> ET.Element:
    for light in world.findall("light"):
        if light.get("name") == "map_sim_sun":
            return light

    for light in world.findall("light"):
        if light.get("type") == "directional":
            light.set("name", "map_sim_sun")
            return light

    light = ET.Element("light", {"name": "map_sim_sun", "type": "directional"})
    world.insert(insert_index if insert_index is not None else 1, light)
    return light


def _configure_sun_light(
    light: ET.Element,
    diffuse: tuple[float, float, float, float],
    specular: tuple[float, float, float, float],
    direction: tuple[float, float, float],
    cast_shadows: bool,
) -> None:
    light.set("name", "map_sim_sun")
    light.set("type", "directional")
    _set_scalar(light, "cast_shadows", "true" if cast_shadows else "false")
    _set_scalar(light, "pose", "0 0 120 0 0 0")
    _set_rgba(light, "diffuse", diffuse)
    _set_rgba(light, "specular", specular)
    _set_scalar(
        light,
        "direction",
        " ".join(_format_scalar(value) for value in direction),
    )


def _ensure_solar_plugin(
    world: ET.Element,
    solar_hours: float,
    light_name: str,
) -> None:
    _remove_solar_plugin(world)
    plugin = ET.Element(
        "plugin",
        {
            "name": SOLAR_PLUGIN_NAME,
            "filename": SOLAR_PLUGIN_FILENAME,
        },
    )
    ET.SubElement(plugin, "light_name").text = light_name
    ET.SubElement(plugin, "topic_name").text = SOLAR_TIME_TOPIC
    ET.SubElement(plugin, "initial_time_hours").text = f"{solar_hours:.6f}"
    world.append(plugin)


def _remove_solar_plugin(world: ET.Element) -> None:
    for child in list(world):
        if child.tag == "plugin" and child.get("name") == SOLAR_PLUGIN_NAME:
            world.remove(child)


def _remove_light_by_name(world: ET.Element, light_name: str) -> None:
    for child in list(world):
        if child.tag == "light" and child.get("name") == light_name:
            world.remove(child)


def _set_rgba(parent: ET.Element, child_name: str, rgba: tuple[float, float, float, float]) -> None:
    child = parent.find(child_name)
    if child is None:
        child = ET.SubElement(parent, child_name)
    child.text = _format_rgba(rgba)


def _set_scalar(parent: ET.Element, child_name: str, value: str) -> None:
    child = parent.find(child_name)
    if child is None:
        child = ET.SubElement(parent, child_name)
    child.text = value


def _parse_rgba(
    text: str | None,
    fallback: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if not text:
        return fallback
    parts = [float(part) for part in text.split()]
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2], fallback[3])
    if len(parts) >= 4:
        return (parts[0], parts[1], parts[2], parts[3])
    return fallback


def _mix_rgba(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    t: float,
) -> tuple[float, float, float, float]:
    t = _clamp01(t)
    return (
        _lerp(left[0], right[0], t),
        _lerp(left[1], right[1], t),
        _lerp(left[2], right[2], t),
        _lerp(left[3], right[3], t),
    )


def _scale_rgba(
    rgba: tuple[float, float, float, float],
    scale: float,
) -> tuple[float, float, float, float]:
    return (
        _clamp01(rgba[0] * scale),
        _clamp01(rgba[1] * scale),
        _clamp01(rgba[2] * scale),
        _clamp01(rgba[3]),
    )


def _format_rgba(rgba: tuple[float, float, float, float]) -> str:
    return " ".join(_format_scalar(value) for value in rgba)


def _format_scalar(value: float) -> str:
    text = f"{value:.4f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _format_time_token(hours: float) -> str:
    total_minutes = int(round(hours * 60.0)) % (24 * 60)
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}_{minute:02d}"


def _lerp(left: float, right: float, t: float) -> float:
    return left + (right - left) * t


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))

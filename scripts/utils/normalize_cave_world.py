#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET


CAVE_WORLD_SCALE = 0.3
SCALED_SUFFIX = "__scaled_0p3"
URI_PREFIX = "model://"
EXCLUDE_SCALED_MODELS = {"Artifact Proximity Detector"}
KNOWN_SCALED_SUFFIXES = ("__scaled_0p2", "__scaled_0p3")


def _format_float(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def _format_pose(values: list[float]) -> str:
    return " ".join(_format_float(value) for value in values)


def _parse_pose_text(text: str | None) -> list[float]:
    raw_values = [float(part) for part in (text or "").split()]
    return (raw_values + [0.0] * 6)[:6]


def _scale_numeric_text(text: str | None, scale: float) -> str | None:
    if text is None:
        return None
    values = [part for part in text.split() if part]
    if not values:
        return text
    return " ".join(_format_float(float(value) * scale) for value in values)


def _looks_like_number(value: str | None) -> bool:
    if value is None:
        return False
    try:
        float(value.strip())
        return True
    except (TypeError, ValueError):
        return False


def _scaled_model_name(model_name: str) -> str:
    return f"{model_name}{SCALED_SUFFIX}"


def _uri_to_model_name(uri: str) -> str | None:
    if not uri.startswith(URI_PREFIX):
        return None
    return uri[len(URI_PREFIX) :].strip()


def _strip_known_scaled_suffix(model_name: str) -> str:
    base_name = model_name
    changed = True
    while changed:
        changed = False
        for suffix in KNOWN_SCALED_SUFFIXES:
            if base_name.endswith(suffix):
                base_name = base_name[: -len(suffix)]
                changed = True
    return base_name


def _scale_pose_element(pose: ET.Element, scale_xyz: float, pose_only_xyz: bool = False) -> bool:
    pose_values = _parse_pose_text(pose.text)
    desired = pose_values[:]
    desired[0] *= scale_xyz
    desired[1] *= scale_xyz
    desired[2] *= scale_xyz
    desired_text = _format_pose(desired)
    if (pose.text or "").strip() != desired_text:
        pose.text = desired_text
        return True
    return False


def _iter_geometry_scale_targets(root: ET.Element):
    for element in root.iter():
        if element.tag == "scale":
            yield element
        elif element.tag == "size":
            yield element
        elif element.tag in {"radius", "length"} and _looks_like_number(element.text):
            yield element


def _ensure_mesh_scales(root: ET.Element, scale: float) -> bool:
    changed = False
    desired_scale = _format_pose([scale, scale, scale])
    for mesh in root.iter("mesh"):
        scale_node = mesh.find("scale")
        if scale_node is None:
            scale_node = ET.SubElement(mesh, "scale")
            scale_node.text = desired_scale
            changed = True
            continue

        if (scale_node.text or "").strip() != desired_scale:
            scale_node.text = desired_scale
            changed = True
    return changed


def _scale_model_tree(root: ET.Element, scale: float, scaled_model_name: str) -> bool:
    changed = False

    model = root.find("model")
    if model is not None and model.get("name") != scaled_model_name:
        model.set("name", scaled_model_name)
        changed = True

    for pose in root.iter("pose"):
        if _scale_pose_element(pose, scale):
            changed = True

    for target in _iter_geometry_scale_targets(root):
        scaled_text = _scale_numeric_text(target.text, scale)
        if scaled_text is not None and (target.text or "").strip() != scaled_text:
            target.text = scaled_text
            changed = True

    if _ensure_mesh_scales(root, scale):
        changed = True

    return changed


def _rewrite_model_config(model_config_path: Path, scaled_model_name: str) -> bool:
    raw_text = model_config_path.read_text(encoding="utf-8", errors="ignore")
    tree = ET.ElementTree(ET.fromstring(raw_text.lstrip()))
    root = tree.getroot()
    changed = False

    name = root.find("name")
    if name is not None and (name.text or "").strip() != scaled_model_name:
        name.text = scaled_model_name
        changed = True

    if changed:
        tree.write(model_config_path, encoding="utf-8", xml_declaration=True)
    return changed


def ensure_scaled_model(model_name: str, model_cache_dir: Path, scale: float) -> str:
    if model_name in EXCLUDE_SCALED_MODELS:
        return model_name

    scaled_name = _scaled_model_name(model_name)
    source_dir = model_cache_dir / model_name
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing source model for cave scaling: {source_dir}")

    target_dir = model_cache_dir / scaled_name
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir, symlinks=True)

    model_sdf_path = target_dir / "model.sdf"
    model_config_path = target_dir / "model.config"

    tree = ET.parse(model_sdf_path)
    root = tree.getroot()
    _scale_model_tree(root, scale, scaled_name)
    tree.write(model_sdf_path, encoding="utf-8", xml_declaration=True)

    if model_config_path.exists():
        _rewrite_model_config(model_config_path, scaled_name)

    return scaled_name


def normalize_cave_world(world_path: Path, model_cache_dir: Path, scale: float) -> bool:
    tree = ET.parse(world_path)
    root = tree.getroot()
    world = root.find("world")
    if world is None:
        raise RuntimeError(f"Missing <world> element in {world_path}")

    changed = False
    scaled_model_names: dict[str, str] = {}

    for include in world.findall("include"):
        uri_node = include.find("uri")
        if uri_node is None or not (uri_node.text or "").strip():
            continue

        uri_text = uri_node.text.strip()
        model_name = _uri_to_model_name(uri_text)
        if model_name is None:
            continue

        canonical_model_name = _strip_known_scaled_suffix(model_name)
        desired_scaled_model_name = _scaled_model_name(canonical_model_name)
        if model_name.endswith(SCALED_SUFFIX):
            source_model_name = canonical_model_name
            if source_model_name and source_model_name not in scaled_model_names:
                if (model_cache_dir / source_model_name).exists():
                    scaled_model_names[source_model_name] = ensure_scaled_model(
                        source_model_name,
                        model_cache_dir,
                        scale,
                    )
            desired_uri = f"{URI_PREFIX}{desired_scaled_model_name}"
            if uri_text != desired_uri:
                uri_node.text = desired_uri
                changed = True
            continue

        if canonical_model_name != model_name:
            desired_uri = f"{URI_PREFIX}{desired_scaled_model_name}"
            if uri_text != desired_uri:
                uri_node.text = desired_uri
                changed = True

            pose = include.find("pose")
            if pose is None:
                pose = ET.SubElement(include, "pose")
                pose.text = "0 0 0 0 0 0"
                changed = True
            continue

        scaled_model_name = scaled_model_names.get(model_name)
        if scaled_model_name is None:
            scaled_model_name = ensure_scaled_model(model_name, model_cache_dir, scale)
            scaled_model_names[model_name] = scaled_model_name

        desired_uri = f"{URI_PREFIX}{scaled_model_name}"
        if uri_text != desired_uri:
            uri_node.text = desired_uri
            changed = True

        pose = include.find("pose")
        if pose is None:
            pose = ET.SubElement(include, "pose")
            pose.text = "0 0 0 0 0 0"
            changed = True

        if _scale_pose_element(pose, scale):
            changed = True

    if changed:
        tree.write(world_path, encoding="utf-8", xml_declaration=True)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize and downscale the LTU cave world so the map feels proportionate "
            "for the sim car."
        )
    )
    parser.add_argument("world_path", help="Path to darpa_cave_01.world")
    parser.add_argument(
        "--model-cache-dir",
        required=True,
        help="Path to the local Gazebo model cache used by the cave world",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=CAVE_WORLD_SCALE,
        help="Uniform XYZ scaling applied to cave world includes and copied models",
    )
    args = parser.parse_args()

    world_path = Path(args.world_path).expanduser().resolve()
    model_cache_dir = Path(args.model_cache_dir).expanduser().resolve()
    changed = normalize_cave_world(world_path, model_cache_dir, args.scale)
    status = "updated" if changed else "already normalized"
    print(f"[cave-world] {status}: {world_path} scale={_format_float(args.scale)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

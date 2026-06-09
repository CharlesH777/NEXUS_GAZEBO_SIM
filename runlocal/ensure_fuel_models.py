#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ARTIFACT_PROXIMITY_REMOTE_URIS = (
    "https://fuel.ignitionrobotics.org/1.0/OpenRobotics/models/Artifact Proximity Detector",
    "https://fuel.gazebosim.org/1.0/OpenRobotics/models/Artifact Proximity Detector",
)


def iter_file_paths(nodes):
    for node in nodes:
        children = node.get("children") or []
        if children:
            yield from iter_file_paths(children)
            continue
        path = node.get("path", "")
        if path:
            yield path


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    destination.write_bytes(data)


def normalize_local_fuel_references(model_dir: Path) -> None:
    model_sdf = model_dir / "model.sdf"
    if not model_sdf.is_file():
        return

    text = model_sdf.read_text()
    updated = text
    for remote_uri in ARTIFACT_PROXIMITY_REMOTE_URIS:
        updated = updated.replace(remote_uri, "model://Artifact Proximity Detector")

    if updated != text:
        model_sdf.write_text(updated)


def extract_local_model_aliases(model_dir: Path) -> set[str]:
    model_sdf = model_dir / "model.sdf"
    if not model_sdf.is_file():
        return set()

    text = model_sdf.read_text()
    aliases = set(re.findall(r"model://([^/\s<]+(?: [^/\s<]+)*)/", text))
    aliases.discard(model_dir.name)
    return {alias for alias in aliases if alias}


def ensure_local_model_aliases(model_dir: Path, destination_root: Path) -> None:
    for alias in sorted(extract_local_model_aliases(model_dir)):
        alias_path = destination_root / alias
        if alias_path == model_dir:
            continue

        if alias_path.is_symlink():
            try:
                if alias_path.resolve() == model_dir.resolve():
                    continue
            except FileNotFoundError:
                pass
            alias_path.unlink()
        elif alias_path.exists():
            continue

        alias_path.symlink_to(model_dir.name, target_is_directory=True)


def ensure_model(owner: str, model_name: str, destination_root: Path, force: bool) -> None:
    model_dir = destination_root / model_name
    if not force and (model_dir / "model.config").is_file() and (model_dir / "model.sdf").is_file():
        normalize_local_fuel_references(model_dir)
        ensure_local_model_aliases(model_dir, destination_root)
        print(f"[fuel] using cached model: {model_name}")
        return

    api_base = (
        "https://fuel.gazebosim.org/1.0/"
        + urllib.parse.quote(owner)
        + "/models/"
        + urllib.parse.quote(model_name)
    )
    tree_url = api_base + "/tip/files"
    with urllib.request.urlopen(tree_url, timeout=60) as response:
        payload = json.load(response)

    file_paths = sorted(set(iter_file_paths(payload.get("file_tree", []))))
    if not file_paths:
        raise RuntimeError(f"Fuel model [{owner}/{model_name}] returned an empty file tree")

    print(f"[fuel] downloading model: {model_name} ({len(file_paths)} files)")
    for remote_path in file_paths:
        relative_path = remote_path.lstrip("/")
        file_url = tree_url + urllib.parse.quote(remote_path, safe="/")
        local_path = model_dir / relative_path
        download_file(file_url, local_path)

    normalize_local_fuel_references(model_dir)
    ensure_local_model_aliases(model_dir, destination_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Gazebo Fuel models into a local model cache."
    )
    parser.add_argument(
        "--owner",
        default="OpenRobotics",
        help="Fuel owner / organization name.",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Destination directory that will contain the model folders.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Model name to download. May be repeated.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload models even if they already exist locally.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model:
        print("[fuel] no models requested", file=sys.stderr)
        return 1

    destination_root = Path(os.path.expanduser(args.dest)).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)

    for model_name in args.model:
        try:
            ensure_model(args.owner, model_name, destination_root, args.force)
        except Exception as exc:  # pragma: no cover - surfaced to shell caller
            print(f"[fuel] failed to download model [{model_name}]: {exc}", file=sys.stderr)
            return 1

    print(f"[fuel] model cache ready: {destination_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

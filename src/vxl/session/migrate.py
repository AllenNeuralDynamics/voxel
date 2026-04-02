# ruff: noqa: T201
"""Migrate legacy session YAML files to current format.

Usage:
    uv run vxl-migrate                          # migrate all sessions in ~/.voxel/playground
    uv run vxl-migrate /path/to/sessions        # migrate sessions in a specific directory
    uv run vxl-migrate /path/to/session.yaml    # migrate a single file

NOTE: Consider introducing a schema version field (e.g. `config_version: 2`) to session YAML
files. This would replace format detection heuristics with explicit versioning, making future
migrations deterministic and allowing SessionConfig.from_yaml to reject unrecognized versions
with a clear error instead of silently misinterpreting data.
"""

import sys
from pathlib import Path
from typing import Any

from ruyaml import YAML

yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


def migrate_session_data(raw: dict[str, Any], session_dir: Path) -> None:  # noqa: C901
    """Migrate legacy session YAML data to current format in-place.

    Detects format version and normalizes to current schema:
    - plan (various formats) -> acq + top-level stacks
    - grid configs -> merged into rig.profiles
    - Adds storage defaults if missing
    - Removes deprecated keys

    Supports:
    1. Current: acq + storage + stacks at top level -> no-op
    2. plan with profile_order (stacks inside plan)
    3. plan with profiles list [{profile_id, grid}] (stacks inside plan)
    4. plan with grid_configs dict (stacks inside plan)
    5. Flat grid_config + stacks at root
    """
    rig = raw.get("rig", {})
    profiles = rig.get("profiles", {})
    globals_cfg = rig.get("globals", {})
    default_tile_order = globals_cfg.get("default_tile_order", "row_wise")

    # Already current format
    if "acq" in raw:
        pass

    elif "plan" in raw:
        plan = raw.pop("plan")

        if "profile_order" in plan:
            raw["acq"] = {
                "profile_order": list(plan["profile_order"]),
                "tile_order": plan.get("tile_order", "row_wise"),
                "interleaving": plan.get("interleaving", "position_first"),
            }

        elif "profiles" in plan and isinstance(plan["profiles"], list):
            profile_order = []
            for p in plan["profiles"]:
                pid = p["profile_id"]
                if pid in profiles and "grid" in p:
                    profiles[pid]["grid"] = p["grid"]
                profile_order.append(pid)
            raw["acq"] = {
                "profile_order": profile_order,
                "tile_order": plan.get("tile_order", "row_wise"),
                "interleaving": plan.get("interleaving", "position_first"),
            }

        elif "grid_configs" in plan:
            profile_order = []
            for pid, gc_data in plan.get("grid_configs", {}).items():
                if pid in profiles:
                    profiles[pid]["grid"] = gc_data
                profile_order.append(pid)
            raw_tile_order = raw.get("tile_order", "row_wise")
            tile_order = default_tile_order if raw_tile_order == "unset" else raw_tile_order
            raw["acq"] = {
                "profile_order": profile_order,
                "tile_order": tile_order,
                "interleaving": "position_first",
            }

        else:
            raw["acq"] = {
                "profile_order": [],
                "tile_order": plan.get("tile_order", "row_wise"),
                "interleaving": plan.get("interleaving", "position_first"),
            }

        raw.setdefault("stacks", plan.get("stacks", []))

    elif "grid_config" in raw:
        old_gc = raw.pop("grid_config")
        stacks = raw.get("stacks", [])
        profile_ids = {s.get("profile_id") for s in stacks if s.get("profile_id")}
        if not profile_ids and profiles:
            profile_ids = {next(iter(profiles))}
        for pid in profile_ids:
            if pid in profiles:
                profiles[pid]["grid"] = old_gc
        raw_tile_order = raw.get("tile_order", "row_wise")
        tile_order = default_tile_order if raw_tile_order == "unset" else raw_tile_order
        raw["acq"] = {
            "profile_order": list(profile_ids),
            "tile_order": tile_order,
            "interleaving": "position_first",
        }

    else:
        raw.setdefault("acq", {"profile_order": [], "tile_order": "row_wise", "interleaving": "position_first"})

    if "storage" not in raw:
        raw["storage"] = {"store_path": str(session_dir / "data")}

    raw.setdefault("stacks", [])

    for key in ("workflow_steps", "workflow_committed", "tile_order", "plan", "grid_config", "acq_settings"):
        raw.pop(key, None)

    for profile in profiles.values():
        if isinstance(profile, dict):
            profile.pop("device_settings", None)


def migrate_file(path: Path) -> bool:
    """Load, migrate, and save a session YAML file. Returns True on success."""
    try:
        with path.open() as f:
            raw_data = yaml.load(f)

        migrate_session_data(raw_data, session_dir=path.parent)

        temp_path = path.with_suffix(".yaml.tmp")
        backup_path = path.with_suffix(".yaml.bak")

        with temp_path.open("w") as f:
            yaml.dump(raw_data, f)

        if path.exists():
            path.replace(backup_path)
        temp_path.replace(path)

        return True
    except Exception as e:
        print(f"  FAIL: {path.parent.name}: {e}")
        return False


def main() -> None:
    """CLI entry point for vxl-migrate."""
    target = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.home() / ".voxel" / "playground"

    if target.is_file() and target.suffix in (".yaml", ".yml"):
        if migrate_file(target):
            print(f"Migrated: {target}")
        else:
            sys.exit(1)
    elif target.is_dir():
        session_files = sorted(target.glob("*/session.voxel.yaml"))
        if not session_files:
            print(f"No session files found in {target}")
            sys.exit(0)

        print(f"Found {len(session_files)} session files in {target}")
        ok = 0
        for sf in session_files:
            if migrate_file(sf):
                print(f"  OK: {sf.parent.name}")
                ok += 1

        print(f"\nMigrated {ok}/{len(session_files)} sessions")
        if ok < len(session_files):
            sys.exit(1)
    else:
        print(f"Not a file or directory: {target}")
        sys.exit(1)

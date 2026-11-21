"""The commands of the legacy app: checking its instrument configs, creating its station, and importing its file
catalog. Only ``vxl legacy`` loads this module."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from uuid import UUID

from pydantic import ValidationError
from vxl_records import RecordsError, SQLiteRecords

from vxl._legacy.instrument.errors import Violation
from vxl._legacy.instrument.store import InstrumentInspection, InstrumentStore
from vxl._legacy.station.station import StationConfig as LegacyStationConfig
from vxl.storage import StorageSpec
from vxl.system import load_voxel_env

from .report import CheckedTarget, write_report
from .station import initialize_with


@dataclass(frozen=True)
class TargetCheck:
    path: Path
    inspection: InstrumentInspection | None = None
    input_violations: tuple[Violation, ...] = ()

    @property
    def ok(self) -> bool:
        return self.inspection is not None and self.inspection.ok

    @property
    def violations(self) -> tuple[Violation, ...]:
        return self.inspection.violations if self.inspection is not None else self.input_violations


def _input_error(path: Path, message: str, code: str) -> TargetCheck:
    return TargetCheck(
        path,
        input_violations=(Violation(code=code, msg=message),),
    )


def _check_path(path: Path) -> TargetCheck:
    if path.is_file():
        return TargetCheck(path, InstrumentStore.load_config(path))
    if path.is_dir() and (path.suffix == ".voxel" or (path / "config.yaml").exists()):
        return TargetCheck(path, InstrumentStore.check(path))
    return _input_error(path, f"Unsupported check target: {path}", "target.unsupported")


def _children(path: Path) -> list[Path]:
    configs = path.glob("*.voxel.yaml")
    instruments = (child for child in path.glob("*.voxel") if child.is_dir())
    return sorted([*configs, *instruments])


def collect_checks(paths: list[Path]) -> list[TargetCheck]:
    """Expand requested files/directories and check each concrete target."""
    if not paths:
        root = LegacyStationConfig.station_dir() / "instruments"
        return [_check_path(path) for path in _children(root)] if root.is_dir() else []

    targets: list[TargetCheck] = []
    for path in paths:
        if not path.exists():
            targets.append(_input_error(path, f"Check target does not exist: {path}", "target.not_found"))
        elif path.is_dir() and path.suffix != ".voxel" and not (path / "config.yaml").exists():
            children = _children(path)
            if children:
                targets.extend(_check_path(child) for child in children)
            else:
                targets.append(_input_error(path, f"No instrument configs found under {path}", "target.empty"))
        else:
            targets.append(_check_path(path))
    return targets


def run_check(paths: list[Path], *, as_json: bool, output: TextIO) -> int:
    """Check targets, render the result, and return a process exit code."""
    load_voxel_env()
    checks = collect_checks(paths)
    targets = [CheckedTarget(checked.path, checked.ok, checked.violations) for checked in checks]
    write_report(targets, as_json=as_json, output=output, nothing="No installed instruments found.")

    if any(
        violation.code is not None and violation.code.startswith("target.")
        for checked in checks
        for violation in checked.violations
    ):
        return 2
    return 0 if all(checked.ok for checked in checks) else 1


def initialize_legacy(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the legacy station's ``station.yaml`` and report a shell-friendly status."""
    return initialize_with(LegacyStationConfig, name, station_id=station_id, output=output, errors=errors)


def import_catalog(*, output: TextIO, errors: TextIO) -> int:
    """Import the legacy file catalog into the station's SQLite records database."""
    load_voxel_env()
    try:
        station = LegacyStationConfig.load()
        records = SQLiteRecords(
            station.station_dir() / "records.sqlite3",
            resolve_root=lambda spec: station.resolve_storage(StorageSpec.model_validate(spec.model_dump())).target,
        )
        result = asyncio.run(records.acquisitions.import_legacy_file_catalog(station.station_dir() / "catalog"))
    except (OSError, RecordsError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2

    output.write(
        f"Imported {result.imported} acquisition(s); {result.unchanged} already matched. "
        "Legacy catalog files were left unchanged.\n"
    )
    return 0


__all__ = ["collect_checks", "import_catalog", "initialize_legacy", "run_check"]

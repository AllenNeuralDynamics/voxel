"""The station's commands: creating its ``station.yaml``, and checking it and its instrument folders."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, Self, TextIO
from uuid import UUID

from pydantic import ValidationError
from vxlib.issues import Problem

from vxl.instrument.folder import InstrumentFolder
from vxl.station.config import StationConfig
from vxl.station.errors import StationNotConfiguredError
from vxl.system import load_voxel_env

from .report import CheckedTarget, write_report


class _Initializable(Protocol):
    """A station config that can write its own ``station.yaml``."""

    id: UUID
    name: str

    @classmethod
    def initialize(cls, name: str, *, station_id: UUID | None = None) -> Self: ...

    @classmethod
    def config_path(cls) -> Path: ...


def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the station's ``station.yaml`` and report a shell-friendly status."""
    return initialize_with(StationConfig, name, station_id=station_id, output=output, errors=errors)


def initialize_with(
    config: type[_Initializable], name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO
) -> int:
    """Create the ``station.yaml`` of ``config`` and report a shell-friendly status."""
    load_voxel_env()
    try:
        station = config.initialize(name, station_id=station_id)
    except (FileExistsError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2
    output.write(f"Initialized control station '{station.name}' ({station.id}) at {station.config_path()}\n")
    return 0


def run_check(paths: Sequence[Path], *, as_json: bool, output: TextIO) -> int:
    """Check instrument folders, or with no ``paths``, ``station.yaml`` and every instrument folder of the station.
    Give back 0 when all is well, 1 when something is wrong, and 2 when a path does not exist."""
    load_voxel_env()
    targets: list[CheckedTarget] = []
    if not paths:
        targets.append(_check_station())
        root = StationConfig.station_dir() / "instruments"
        paths = sorted(root.glob("*.voxel")) if root.is_dir() else []
    missing = False
    for path in paths:
        if not path.is_dir():
            missing = True
            problem = Problem(code="target.not_found", msg=f"No instrument folder at {path}")
            targets.append(CheckedTarget(path, ok=False, findings=(problem,)))
            continue
        folder = InstrumentFolder.read(path)
        targets.append(CheckedTarget(path, ok=folder.ok, findings=tuple(folder.problems)))
    write_report(targets, as_json=as_json, output=output, nothing="Nothing to check.")
    if missing:
        return 2
    return 0 if all(target.ok for target in targets) else 1


def _check_station() -> CheckedTarget:
    """Whether ``station.yaml`` loads."""
    path = StationConfig.config_path()
    try:
        StationConfig.load()
    except (StationNotConfiguredError, ValidationError, ValueError) as error:
        return CheckedTarget(path, ok=False, findings=(Problem(code="station.load", msg=str(error)),))
    return CheckedTarget(path, ok=True)


__all__ = ["initialize", "initialize_with", "run_check"]

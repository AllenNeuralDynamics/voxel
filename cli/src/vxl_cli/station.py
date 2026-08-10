"""Control-station configuration commands."""

from typing import TextIO
from uuid import UUID

from pydantic import ValidationError

from vxl.system import Station, load_voxel_env


def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the local ``station.yaml`` and report a shell-friendly status."""
    load_voxel_env()
    try:
        station = Station.initialize(name, station_id=station_id)
    except (FileExistsError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2

    output.write(f"Initialized control station '{station.name}' ({station.id}) at {station.config_path()}\n")
    return 0


__all__ = ["initialize"]

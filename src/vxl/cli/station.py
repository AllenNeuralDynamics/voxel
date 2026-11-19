"""Control-station configuration commands."""

import asyncio
from typing import TextIO
from uuid import UUID

from pydantic import ValidationError
from vxl_records import RecordsError, SQLiteRecords

from vxl.core.station import StationConfig
from vxl.station_legacy.config import StationNotConfiguredError
from vxl.station_legacy.station import StationConfig as LegacyStationConfig
from vxl.system import load_voxel_env


def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the station's ``station.yaml`` and report a shell-friendly status."""
    return _initialize(StationConfig, name, station_id=station_id, output=output, errors=errors)


def initialize_legacy(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the legacy station's ``station.yaml`` and report a shell-friendly status."""
    return _initialize(LegacyStationConfig, name, station_id=station_id, output=output, errors=errors)


def _initialize(
    config: type[StationConfig | LegacyStationConfig],
    name: str,
    *,
    station_id: UUID | None,
    output: TextIO,
    errors: TextIO,
) -> int:
    load_voxel_env()
    try:
        station = config.initialize(name, station_id=station_id)
    except (FileExistsError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2

    output.write(f"Initialized control station '{station.name}' ({station.id}) at {station.config_path()}\n")
    return 0


def import_catalog(*, output: TextIO, errors: TextIO) -> int:
    """Import the legacy file catalog into the station's SQLite records database."""
    load_voxel_env()
    try:
        station = LegacyStationConfig.load()
        records = SQLiteRecords(
            station.dir / "records.sqlite3",
            resolve_root=lambda spec: station.resolve_storage(spec).target,
        )
        result = asyncio.run(records.acquisitions.import_legacy_file_catalog(station.dir / "catalog"))
    except (OSError, RecordsError, StationNotConfiguredError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2

    output.write(
        f"Imported {result.imported} acquisition(s); {result.unchanged} already matched. "
        "Legacy catalog files were left unchanged.\n"
    )
    return 0


__all__ = ["import_catalog", "initialize", "initialize_legacy"]

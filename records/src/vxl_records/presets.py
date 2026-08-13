"""Instrument-scoped preset records backed by SQLite."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import TYPE_CHECKING

from .errors import PresetExistsError, PresetNotFoundError
from .models import PresetRecord

if TYPE_CHECKING:
    from sqlite3 import Row
    from uuid import UUID

    from ._sqlite import SQLiteDatabase


class PresetCatalog:
    """Persist and query named reusable configuration payloads by instrument."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    async def create(self, preset: PresetRecord) -> PresetRecord:
        """Create a preset, rejecting duplicate IDs or names within its instrument."""
        await asyncio.to_thread(self._create, preset)
        return preset

    async def get(self, preset_id: UUID) -> PresetRecord:
        """Return one preset by its stable identity."""
        preset = await asyncio.to_thread(self._get, preset_id)
        if preset is None:
            raise PresetNotFoundError(f"preset not found: {preset_id}")
        return preset

    async def list(self, instrument: str) -> list[PresetRecord]:
        """Return one instrument's presets, newest first."""
        return await asyncio.to_thread(self._list, instrument)

    async def delete(self, preset_id: UUID) -> None:
        """Permanently delete one preset record."""
        deleted = await asyncio.to_thread(self._delete, preset_id)
        if not deleted:
            raise PresetNotFoundError(f"preset not found: {preset_id}")

    def _create(self, preset: PresetRecord) -> None:
        with self._database.transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO presets (id, instrument, name, created_at_us, preset_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(preset.id),
                        preset.instrument,
                        preset.name,
                        int(preset.created_at.timestamp() * 1_000_000),
                        preset.model_dump_json(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise PresetExistsError(
                    f"preset ID or instrument/name already exists: {preset.id} ({preset.instrument}/{preset.name})"
                ) from error

    def _get(self, preset_id: UUID) -> PresetRecord | None:
        connection = self._database.connect()
        try:
            row = connection.execute("SELECT preset_json FROM presets WHERE id = ?", (str(preset_id),)).fetchone()
            return self._from_row(row) if row is not None else None
        finally:
            connection.close()

    def _list(self, instrument: str) -> list[PresetRecord]:
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT preset_json FROM presets WHERE instrument = ? ORDER BY created_at_us DESC, id",
                (instrument,),
            ).fetchall()
            return [self._from_row(row) for row in rows]
        finally:
            connection.close()

    def _delete(self, preset_id: UUID) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM presets WHERE id = ?", (str(preset_id),))
            return cursor.rowcount == 1

    @staticmethod
    def _from_row(row: Row) -> PresetRecord:
        return PresetRecord.model_validate_json(row["preset_json"])


__all__ = ["PresetCatalog"]

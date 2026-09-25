"""Revisioned acquisition records backed by SQLite."""

from __future__ import annotations

import asyncio
import datetime
import os
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from cloudpathlib import S3Path

from .errors import (
    LegacyImportError,
    ManifestExistsError,
    ManifestNotFoundError,
    ManifestSyncError,
    RevisionConflictError,
)
from .models import (
    AcquisitionFailure,
    AcquisitionManifest,
    Dataset,
    DatasetLocation,
    DatasetStatus,
    LocationStatus,
    StorageSpec,
    VolumeStatus,
)

if TYPE_CHECKING:
    from sqlite3 import Connection, Row

    from ._sqlite import SQLiteDatabase

type StorageRootResolver = Callable[[StorageSpec], Path | S3Path]
type ManifestEdit = Callable[[AcquisitionManifest], AcquisitionManifest]


@dataclass(frozen=True)
class LegacyImportResult:
    """Summary of one non-destructive legacy file-catalog import."""

    imported: int
    unchanged: int


@dataclass(frozen=True)
class _LegacyManifest:
    manifest: AcquisitionManifest
    archived_at_us: int | None


class _ManifestProjection:
    """Write the portable manifest projection to an acquisition's resolved root."""

    def __init__(self, resolve_root: StorageRootResolver) -> None:
        self._resolve_root = resolve_root

    async def write(self, manifest: AcquisitionManifest) -> None:
        await asyncio.to_thread(self._write, manifest)

    def _write(self, manifest: AcquisitionManifest) -> None:
        root = self._resolve_root(manifest.storage)
        root.mkdir(parents=True, exist_ok=True)
        payload = f"{manifest.model_dump_json(indent=2)}\n"

        if isinstance(root, S3Path):
            (root / "manifest.json").write_text(payload, encoding="utf-8")
            return

        path = root / "manifest.json"
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)


def _datetime_to_unix_us(value: datetime.datetime) -> int:
    return int(value.timestamp() * 1_000_000)


class AcquisitionCatalog:
    """Persist revisioned acquisition manifests and their portable projections."""

    def __init__(self, database: SQLiteDatabase, *, resolve_root: StorageRootResolver) -> None:
        self._database = database
        self._projection = _ManifestProjection(resolve_root)

    async def create(self, manifest: AcquisitionManifest) -> AcquisitionManifest:
        """Create a revision-one acquisition and its portable manifest projection."""
        if manifest.revision != 1:
            raise RevisionConflictError(f"new manifest must have revision 1, got {manifest.revision}")
        await asyncio.to_thread(self._create, manifest)
        await self._project(manifest)
        return manifest

    async def get(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Return one unarchived acquisition manifest."""
        manifest = await asyncio.to_thread(self._get, acquisition_id, False)
        if manifest is None:
            raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")
        return manifest

    async def list_manifests(self) -> list[AcquisitionManifest]:
        """Return unarchived acquisition manifests, newest first."""
        return await asyncio.to_thread(self._list_manifests)

    async def start_acquisition(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Mark a prepared acquisition as running."""
        at = _utc_now()

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.start(at)

        return await self._commit(acquisition_id, edit)

    async def complete_acquisition(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Mark a running acquisition as completed."""
        at = _utc_now()

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.complete(at)

        return await self._commit(acquisition_id, edit)

    async def fail_acquisition(
        self,
        acquisition_id: UUID,
        error: BaseException | AcquisitionFailure,
    ) -> AcquisitionManifest:
        """Fail a running acquisition and terminalize every unfinished volume."""
        at = _utc_now()
        failure = (
            error
            if isinstance(error, AcquisitionFailure)
            else AcquisitionFailure(kind=type(error).__name__, message=str(error) or repr(error))
        )

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.fail(failure, at)

        return await self._commit(acquisition_id, edit)

    async def cancel_acquisition(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Cancel a running acquisition and every unfinished volume."""
        at = _utc_now()

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.cancel(at)

        return await self._commit(acquisition_id, edit)

    async def start_volume(self, acquisition_id: UUID, *, volume_index: int) -> AcquisitionManifest:
        """Mark one planned volume as running."""

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.start_volume(volume_index)

        return await self._commit(acquisition_id, edit)

    async def register_datasets(
        self,
        acquisition_id: UUID,
        *,
        volume_index: int,
        locations: Mapping[str, DatasetLocation],
    ) -> AcquisitionManifest:
        """Register each channel's writer location for one running volume."""
        datasets = {
            channel: Dataset(status=DatasetStatus.WRITING, locations=[location])
            for channel, location in locations.items()
        }

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.register_datasets(volume_index, datasets)

        return await self._commit(acquisition_id, edit)

    async def complete_volume(
        self,
        acquisition_id: UUID,
        *,
        volume_index: int,
    ) -> AcquisitionManifest:
        """Atomically make a volume and all its datasets available and complete."""

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.complete_volume(volume_index)

        return await self._commit(acquisition_id, edit)

    async def fail_volume(
        self,
        acquisition_id: UUID,
        *,
        volume_index: int,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> AcquisitionManifest:
        """Fail a volume and atomically terminalize its registered datasets."""

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.terminalize_volume(
                volume_index,
                VolumeStatus.FAILED,
                dataset_status=dataset_status,
                location_status=location_status,
            )

        return await self._commit(acquisition_id, edit)

    async def cancel_volume(
        self,
        acquisition_id: UUID,
        *,
        volume_index: int,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> AcquisitionManifest:
        """Cancel a volume and atomically terminalize its registered datasets."""

        def edit(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return manifest.terminalize_volume(
                volume_index,
                VolumeStatus.CANCELLED,
                dataset_status=dataset_status,
                location_status=location_status,
            )

        return await self._commit(acquisition_id, edit)

    async def sync_manifest(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Rewrite an acquisition-root manifest from the authoritative SQLite revision."""
        manifest = await self.get(acquisition_id)
        await self._project(manifest)
        return manifest

    async def archive(self, acquisition_id: UUID) -> None:
        """Archive an acquisition record without deleting acquired data."""
        archived = await asyncio.to_thread(self._archive, acquisition_id)
        if not archived:
            raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")

    async def import_legacy_file_catalog(self, root: Path | str) -> LegacyImportResult:
        """Import a legacy manifest directory transactionally without modifying its files."""
        return await asyncio.to_thread(self._import_legacy_file_catalog, Path(root))

    def _create(self, manifest: AcquisitionManifest) -> None:
        with self._database.transaction() as connection:
            try:
                self._insert_manifest(connection, manifest, archived_at_us=None)
            except sqlite3.IntegrityError as error:
                if self._select_manifest(connection, manifest.id, include_archived=True) is not None:
                    raise ManifestExistsError(f"acquisition already exists: {manifest.id}") from error
                raise

    def _get(self, acquisition_id: UUID, include_archived: bool) -> AcquisitionManifest | None:
        connection = self._database.connect()
        try:
            row = self._select_manifest(connection, acquisition_id, include_archived=include_archived)
            return self._manifest_from_row(row) if row is not None else None
        finally:
            connection.close()

    def _list_manifests(self) -> list[AcquisitionManifest]:
        connection = self._database.connect()
        try:
            rows = connection.execute(
                "SELECT manifest_json FROM acquisitions WHERE archived_at_us IS NULL ORDER BY created_at_us DESC, id"
            ).fetchall()
            return [self._manifest_from_row(row) for row in rows]
        finally:
            connection.close()

    def _commit_sqlite(self, acquisition_id: UUID, edit: ManifestEdit) -> AcquisitionManifest:
        with self._database.transaction() as connection:
            row = self._select_manifest(connection, acquisition_id, include_archived=False)
            if row is None:
                raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")
            current = self._manifest_from_row(row)
            updated = edit(current)
            if updated == current:
                return current

            updated = AcquisitionManifest.model_validate({**updated.model_dump(), "revision": current.revision + 1})
            cursor = connection.execute(
                "UPDATE acquisitions "
                "SET revision = ?, status = ?, created_at_us = ?, manifest_json = ? "
                "WHERE id = ? AND revision = ? AND archived_at_us IS NULL",
                (
                    updated.revision,
                    updated.status.value,
                    _datetime_to_unix_us(updated.created_at),
                    updated.model_dump_json(),
                    str(updated.id),
                    current.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise RevisionConflictError(f"acquisition revision changed while updating: {acquisition_id}")
            return updated

    def _archive(self, acquisition_id: UUID) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE acquisitions SET archived_at_us = ? WHERE id = ? AND archived_at_us IS NULL",
                (_datetime_to_unix_us(_utc_now()), str(acquisition_id)),
            )
            return cursor.rowcount == 1

    def _import_legacy_file_catalog(self, root: Path) -> LegacyImportResult:
        legacy = self._read_legacy_manifests(root)
        imported = 0
        unchanged = 0
        with self._database.transaction() as connection:
            for entry in legacy:
                existing = self._select_manifest(connection, entry.manifest.id, include_archived=True)
                if existing is None:
                    self._insert_manifest(connection, entry.manifest, archived_at_us=entry.archived_at_us)
                    imported += 1
                    continue

                existing_manifest = self._manifest_from_row(existing)
                existing_archived = existing["archived_at_us"] is not None
                incoming_archived = entry.archived_at_us is not None
                if existing_manifest != entry.manifest or existing_archived != incoming_archived:
                    raise LegacyImportError(f"legacy acquisition conflicts with SQLite record: {entry.manifest.id}")
                unchanged += 1
        return LegacyImportResult(imported=imported, unchanged=unchanged)

    @staticmethod
    def _read_legacy_manifests(root: Path) -> list[_LegacyManifest]:
        if not root.is_dir():
            return []
        candidates = [*(root.glob("*/manifest.json")), *((root / ".archive").glob("*/manifest.json"))]
        found: dict[UUID, _LegacyManifest] = {}
        for path in sorted(candidates):
            try:
                manifest = AcquisitionManifest.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as error:
                raise LegacyImportError(f"invalid legacy manifest: {path}") from error
            if path.parent.name != str(manifest.id):
                raise LegacyImportError(f"legacy manifest ID does not match its directory: {path}")
            archived_at_us = path.stat().st_mtime_ns // 1_000 if path.parent.parent.name == ".archive" else None
            entry = _LegacyManifest(manifest=manifest, archived_at_us=archived_at_us)
            if manifest.id in found:
                raise LegacyImportError(f"duplicate legacy acquisition: {manifest.id}")
            found[manifest.id] = entry
        return list(found.values())

    @staticmethod
    def _insert_manifest(
        connection: Connection,
        manifest: AcquisitionManifest,
        *,
        archived_at_us: int | None,
    ) -> None:
        connection.execute(
            "INSERT INTO acquisitions "
            "(id, revision, status, created_at_us, archived_at_us, manifest_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(manifest.id),
                manifest.revision,
                manifest.status.value,
                _datetime_to_unix_us(manifest.created_at),
                archived_at_us,
                manifest.model_dump_json(),
            ),
        )

    @staticmethod
    def _select_manifest(connection: Connection, acquisition_id: UUID, *, include_archived: bool) -> Row | None:
        query = "SELECT manifest_json, archived_at_us FROM acquisitions WHERE id = ?"
        if not include_archived:
            query += " AND archived_at_us IS NULL"
        return connection.execute(query, (str(acquisition_id),)).fetchone()

    @staticmethod
    def _manifest_from_row(row: Row) -> AcquisitionManifest:
        return AcquisitionManifest.model_validate_json(row["manifest_json"])

    async def _commit(self, acquisition_id: UUID, edit: ManifestEdit) -> AcquisitionManifest:
        committed = await asyncio.to_thread(self._commit_sqlite, acquisition_id, edit)
        await self._project(committed)
        return committed

    async def _project(self, manifest: AcquisitionManifest) -> None:
        try:
            await self._projection.write(manifest)
        except Exception as error:
            raise ManifestSyncError(
                f"acquisition revision {manifest.revision} was committed, but its acquisition-root "
                f"manifest could not be written: {manifest.id}"
            ) from error


__all__ = ["AcquisitionCatalog", "LegacyImportResult", "StorageRootResolver"]

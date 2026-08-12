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
    InvalidTransitionError,
    LegacyImportError,
    ManifestExistsError,
    ManifestNotFoundError,
    ManifestSyncError,
    RevisionConflictError,
)
from .models import (
    AcquisitionFailure,
    AcquisitionManifest,
    AcquisitionStatus,
    AcquisitionVolume,
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
type ManifestTransform = Callable[[AcquisitionManifest], AcquisitionManifest]


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


_ACQUISITION_TRANSITIONS = {
    AcquisitionStatus.PREPARING: {
        AcquisitionStatus.RUNNING,
        AcquisitionStatus.FAILED,
        AcquisitionStatus.CANCELLED,
        AcquisitionStatus.INTERRUPTED,
    },
    AcquisitionStatus.RUNNING: {
        AcquisitionStatus.COMPLETED,
        AcquisitionStatus.FAILED,
        AcquisitionStatus.CANCELLED,
        AcquisitionStatus.INTERRUPTED,
    },
}
_VOLUME_TRANSITIONS = {
    VolumeStatus.PENDING: {
        VolumeStatus.RUNNING,
        VolumeStatus.FAILED,
        VolumeStatus.CANCELLED,
        VolumeStatus.SKIPPED,
    },
    VolumeStatus.RUNNING: {
        VolumeStatus.COMPLETED,
        VolumeStatus.FAILED,
        VolumeStatus.CANCELLED,
    },
}
_DATASET_TRANSITIONS = {
    DatasetStatus.PENDING: {
        DatasetStatus.WRITING,
        DatasetStatus.PARTIAL,
        DatasetStatus.FAILED,
    },
    DatasetStatus.WRITING: {
        DatasetStatus.COMPLETED,
        DatasetStatus.PARTIAL,
        DatasetStatus.FAILED,
    },
}


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.UTC)


def _datetime_to_unix_us(value: datetime.datetime) -> int:
    return int(value.timestamp() * 1_000_000)


class AcquisitionCatalog:
    """Own acquisition lifecycle invariants and durable SQLite records."""

    def __init__(self, database: SQLiteDatabase, *, resolve_root: StorageRootResolver) -> None:
        self._database = database
        self._projection = _ManifestProjection(resolve_root)

    async def create(self, manifest: AcquisitionManifest) -> AcquisitionManifest:
        """Create a revision-one acquisition and its portable manifest projection."""
        if manifest.revision != 1:
            raise RevisionConflictError(f"new manifest must have revision 1, got {manifest.revision}")
        await asyncio.to_thread(self._create, manifest)
        await self._write_manifest(manifest)
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
        return await self._update(
            acquisition_id,
            lambda manifest: self._set_acquisition_status(
                manifest,
                status=AcquisitionStatus.RUNNING,
                at=at,
            ),
        )

    async def complete_acquisition(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Mark a running acquisition as completed."""
        at = _utc_now()
        return await self._update(
            acquisition_id,
            lambda manifest: self._set_acquisition_status(
                manifest,
                status=AcquisitionStatus.COMPLETED,
                at=at,
            ),
        )

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

        def fail(manifest: AcquisitionManifest) -> AcquisitionManifest:
            volumes = [
                self._set_volume_status(volume, VolumeStatus.FAILED)
                if volume.status is VolumeStatus.RUNNING
                else self._set_volume_status(volume, VolumeStatus.SKIPPED)
                if volume.status is VolumeStatus.PENDING
                else volume
                for volume in manifest.volumes
            ]
            manifest = manifest.model_copy(update={"volumes": volumes})
            return self._set_acquisition_status(
                manifest,
                status=AcquisitionStatus.FAILED,
                at=at,
                failure=failure,
            )

        return await self._update(acquisition_id, fail)

    async def cancel_acquisition(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Cancel a running acquisition and every unfinished volume."""
        at = _utc_now()

        def cancel(manifest: AcquisitionManifest) -> AcquisitionManifest:
            volumes = [
                self._set_volume_status(volume, VolumeStatus.CANCELLED)
                if volume.status in {VolumeStatus.PENDING, VolumeStatus.RUNNING}
                else volume
                for volume in manifest.volumes
            ]
            manifest = manifest.model_copy(update={"volumes": volumes})
            return self._set_acquisition_status(
                manifest,
                status=AcquisitionStatus.CANCELLED,
                at=at,
            )

        return await self._update(acquisition_id, cancel)

    async def start_volume(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
    ) -> AcquisitionManifest:
        """Mark one planned task/profile volume as running."""
        return await self._update(
            acquisition_id,
            lambda manifest: self._update_volume(
                manifest,
                task=task,
                profile=profile,
                update=lambda volume: self._set_volume_status(volume, VolumeStatus.RUNNING),
            ),
        )

    async def register_datasets(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
        locations: Mapping[str, DatasetLocation],
    ) -> AcquisitionManifest:
        """Register each channel's writer location for one running volume."""
        datasets = {
            channel: Dataset(status=DatasetStatus.WRITING, locations=[location])
            for channel, location in locations.items()
        }

        def register(manifest: AcquisitionManifest) -> AcquisitionManifest:
            return self._update_volume(
                manifest,
                task=task,
                profile=profile,
                update=lambda volume: self._register_datasets(volume, datasets),
            )

        return await self._update(acquisition_id, register)

    async def complete_volume(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
    ) -> AcquisitionManifest:
        """Atomically make a volume and all its datasets available and complete."""

        def complete(volume: AcquisitionVolume) -> AcquisitionVolume:
            datasets = {
                channel: self._terminalize_dataset(
                    dataset,
                    status=DatasetStatus.COMPLETED,
                    location_status=LocationStatus.AVAILABLE,
                )
                for channel, dataset in volume.datasets.items()
            }
            volume = volume.model_copy(update={"datasets": datasets})
            return self._set_volume_status(volume, VolumeStatus.COMPLETED)

        return await self._update(
            acquisition_id,
            lambda manifest: self._update_volume(
                manifest,
                task=task,
                profile=profile,
                update=complete,
            ),
        )

    async def fail_volume(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> AcquisitionManifest:
        """Fail a volume and atomically terminalize its registered datasets."""
        return await self._terminalize_volume(
            acquisition_id,
            task=task,
            profile=profile,
            volume_status=VolumeStatus.FAILED,
            dataset_status=dataset_status,
            location_status=location_status,
        )

    async def cancel_volume(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> AcquisitionManifest:
        """Cancel a volume and atomically terminalize its registered datasets."""
        return await self._terminalize_volume(
            acquisition_id,
            task=task,
            profile=profile,
            volume_status=VolumeStatus.CANCELLED,
            dataset_status=dataset_status,
            location_status=location_status,
        )

    async def sync_manifest(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Rewrite an acquisition-root manifest from the authoritative SQLite revision."""
        manifest = await self.get(acquisition_id)
        await self._write_manifest(manifest)
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

    def _update_record(self, acquisition_id: UUID, transform: ManifestTransform) -> AcquisitionManifest:
        with self._database.transaction() as connection:
            row = self._select_manifest(connection, acquisition_id, include_archived=False)
            if row is None:
                raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")
            current = self._manifest_from_row(row)
            updated = transform(current)
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

    async def _update(self, acquisition_id: UUID, transform: ManifestTransform) -> AcquisitionManifest:
        updated = await asyncio.to_thread(self._update_record, acquisition_id, transform)
        await self._write_manifest(updated)
        return updated

    async def _write_manifest(self, manifest: AcquisitionManifest) -> None:
        try:
            await self._projection.write(manifest)
        except Exception as error:
            raise ManifestSyncError(
                f"acquisition revision {manifest.revision} was committed, but its acquisition-root "
                f"manifest could not be written: {manifest.id}"
            ) from error

    async def _terminalize_volume(
        self,
        acquisition_id: UUID,
        *,
        task: str,
        profile: str,
        volume_status: VolumeStatus,
        dataset_status: DatasetStatus,
        location_status: LocationStatus,
    ) -> AcquisitionManifest:
        if dataset_status not in {DatasetStatus.PARTIAL, DatasetStatus.FAILED}:
            raise ValueError("a failed or cancelled volume requires partial or failed datasets")
        if location_status not in {LocationStatus.AVAILABLE, LocationStatus.FAILED}:
            raise ValueError("a failed or cancelled volume requires available or failed locations")

        def terminalize(volume: AcquisitionVolume) -> AcquisitionVolume:
            datasets = {
                channel: self._terminalize_dataset(
                    dataset,
                    status=dataset_status,
                    location_status=location_status,
                )
                if dataset.status in {DatasetStatus.PENDING, DatasetStatus.WRITING}
                else dataset
                for channel, dataset in volume.datasets.items()
            }
            volume = volume.model_copy(update={"datasets": datasets})
            if volume.status in {VolumeStatus.PENDING, VolumeStatus.RUNNING}:
                return self._set_volume_status(volume, volume_status)
            return volume

        return await self._update(
            acquisition_id,
            lambda manifest: self._update_volume(
                manifest,
                task=task,
                profile=profile,
                update=terminalize,
            ),
        )

    @staticmethod
    def _set_acquisition_status(
        manifest: AcquisitionManifest,
        *,
        status: AcquisitionStatus,
        at: datetime.datetime,
        failure: AcquisitionFailure | None = None,
    ) -> AcquisitionManifest:
        if status == manifest.status:
            return manifest
        allowed = _ACQUISITION_TRANSITIONS.get(manifest.status, set())
        if status not in allowed:
            raise InvalidTransitionError(f"acquisition cannot transition from {manifest.status} to {status}")
        if status in {AcquisitionStatus.FAILED, AcquisitionStatus.INTERRUPTED} and failure is None:
            raise InvalidTransitionError(f"{status} requires failure details")
        if status not in {AcquisitionStatus.FAILED, AcquisitionStatus.INTERRUPTED} and failure is not None:
            raise InvalidTransitionError(f"{status} cannot carry failure details")

        changes: dict[str, object] = {"status": status, "failure": failure}
        if status is AcquisitionStatus.RUNNING:
            changes["started_at"] = at
        elif status in {
            AcquisitionStatus.COMPLETED,
            AcquisitionStatus.FAILED,
            AcquisitionStatus.CANCELLED,
            AcquisitionStatus.INTERRUPTED,
        }:
            changes["ended_at"] = at
        return manifest.model_copy(update=changes)

    @staticmethod
    def _set_volume_status(volume: AcquisitionVolume, status: VolumeStatus) -> AcquisitionVolume:
        if status == volume.status:
            return volume
        if status not in _VOLUME_TRANSITIONS.get(volume.status, set()):
            raise InvalidTransitionError(f"volume cannot transition from {volume.status} to {status}")
        return volume.model_copy(update={"status": status})

    @staticmethod
    def _set_dataset_status(dataset: Dataset, status: DatasetStatus) -> Dataset:
        if status == dataset.status:
            return dataset
        if status not in _DATASET_TRANSITIONS.get(dataset.status, set()):
            raise InvalidTransitionError(f"dataset cannot transition from {dataset.status} to {status}")
        return dataset.model_copy(update={"status": status})

    @classmethod
    def _terminalize_dataset(
        cls,
        dataset: Dataset,
        *,
        status: DatasetStatus,
        location_status: LocationStatus,
    ) -> Dataset:
        locations = [location.model_copy(update={"status": location_status}) for location in dataset.locations]
        dataset = dataset.model_copy(update={"locations": locations})
        return cls._set_dataset_status(dataset, status)

    @staticmethod
    def _register_datasets(volume: AcquisitionVolume, datasets: Mapping[str, Dataset]) -> AcquisitionVolume:
        registered = dict(volume.datasets)
        for channel, dataset in datasets.items():
            if current := registered.get(channel):
                if current != dataset:
                    raise InvalidTransitionError(f"dataset already registered for channel '{channel}'")
            else:
                registered[channel] = dataset
        return volume.model_copy(update={"datasets": registered})

    @staticmethod
    def _update_volume(
        manifest: AcquisitionManifest,
        *,
        task: str,
        profile: str,
        update: Callable[[AcquisitionVolume], AcquisitionVolume],
    ) -> AcquisitionManifest:
        found = False
        volumes = []
        for volume in manifest.volumes:
            updated_volume = volume
            if volume.task == task and volume.profile == profile:
                updated_volume = update(volume)
                found = True
            volumes.append(updated_volume)
        if not found:
            raise ManifestNotFoundError(f"volume not found: task={task}, profile={profile}")
        return manifest.model_copy(update={"volumes": volumes})


__all__ = ["AcquisitionCatalog", "LegacyImportResult", "StorageRootResolver"]

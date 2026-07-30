"""Concrete acquisition catalog with revisioned lifecycle updates."""

import asyncio
import datetime
import os
import threading
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import UUID

from cloudpathlib import S3Path

from .backend import CatalogBackend
from .errors import (
    InvalidTransitionError,
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

type StorageRootResolver = Callable[[StorageSpec], Path | S3Path]
type ManifestTransform = Callable[[AcquisitionManifest], AcquisitionManifest]


class _ManifestStore:
    """Write ``manifest.json`` to a resolved acquisition root."""

    def __init__(self, resolve_root: StorageRootResolver) -> None:
        self._resolve_root = resolve_root

    async def write(self, manifest: AcquisitionManifest) -> None:
        """Persist the latest manifest revision beside the acquisition's datasets."""
        await asyncio.to_thread(self._write, manifest)

    def _write(self, manifest: AcquisitionManifest) -> None:
        root = self._resolve_root(manifest.storage)
        root.mkdir(parents=True, exist_ok=True)
        path = root / "manifest.json"
        payload = f"{manifest.model_dump_json(indent=2)}\n"

        if isinstance(root, S3Path):
            # An object PUT becomes visible atomically; cloud paths do not offer a portable fsync/rename.
            path.write_text(payload, encoding="utf-8")
            return

        local_path = root / "manifest.json"
        temporary = local_path.with_name(f".{local_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(local_path)
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


class Catalog:
    """Own acquisition manifest CRUD, lifecycle invariants, and revisions."""

    def __init__(
        self,
        backend: CatalogBackend,
        *,
        resolve_root: StorageRootResolver,
        max_conflict_retries: int = 4,
    ) -> None:
        self._backend = backend
        self._manifest_store = _ManifestStore(resolve_root)
        self._max_conflict_retries = max_conflict_retries
        self._mutation_locks: dict[UUID, asyncio.Lock] = {}
        self._mutation_locks_guard = threading.Lock()

    async def create(self, manifest: AcquisitionManifest) -> AcquisitionManifest:
        """Create a revision-one manifest."""
        async with self._mutation_lock(manifest.id):
            if manifest.revision != 1:
                raise RevisionConflictError(f"new manifest must have revision 1, got {manifest.revision}")
            if not await self._backend.create(manifest):
                raise ManifestExistsError(f"acquisition already exists: {manifest.id}")
            await self._write_manifest(manifest)
            return manifest

    async def get(self, acquisition_id: UUID) -> AcquisitionManifest:
        """Return one active acquisition manifest."""
        manifest = await self._backend.get(acquisition_id)
        if manifest is None:
            raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")
        return manifest

    async def list_manifests(self) -> list[AcquisitionManifest]:
        """Return active manifests, newest first."""
        manifests = await self._backend.list_manifests()
        return sorted(manifests, key=lambda manifest: manifest.created_at, reverse=True)

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
        """Mark one planned volume as running."""
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
        """Rewrite the acquisition-root manifest from the catalog's latest indexed revision."""
        async with self._mutation_lock(acquisition_id):
            manifest = await self.get(acquisition_id)
            await self._write_manifest(manifest)
            return manifest

    async def archive(self, acquisition_id: UUID) -> None:
        """Archive a manifest without deleting acquired data."""
        async with self._mutation_lock(acquisition_id):
            if not await self._backend.archive(acquisition_id):
                raise ManifestNotFoundError(f"acquisition not found: {acquisition_id}")

    async def _update(self, acquisition_id: UUID, transform: ManifestTransform) -> AcquisitionManifest:
        """Atomically transform a manifest and increment its revision once."""
        async with self._mutation_lock(acquisition_id):
            for _ in range(self._max_conflict_retries + 1):
                current = await self.get(acquisition_id)
                updated = transform(current)
                if updated == current:
                    return current

                updated = AcquisitionManifest.model_validate({**updated.model_dump(), "revision": current.revision + 1})
                if await self._backend.compare_and_swap(updated, expected_revision=current.revision):
                    await self._write_manifest(updated)
                    return updated

        raise RevisionConflictError(f"acquisition changed repeatedly while updating: {acquisition_id}")

    def _mutation_lock(self, acquisition_id: UUID) -> asyncio.Lock:
        with self._mutation_locks_guard:
            return self._mutation_locks.setdefault(acquisition_id, asyncio.Lock())

    async def _write_manifest(self, manifest: AcquisitionManifest) -> None:
        try:
            await self._manifest_store.write(manifest)
        except Exception as error:
            raise ManifestSyncError(
                f"catalog revision {manifest.revision} was indexed, but its acquisition-root manifest "
                f"could not be written: {manifest.id}"
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

import asyncio
import datetime
import json
import threading
from pathlib import Path, PurePosixPath
from uuid import UUID

import pytest
from vxl_catalog import (
    AcquisitionFailure,
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionStatus,
    AcquisitionVolume,
    Catalog,
    DatasetStatus,
    FileCatalogBackend,
    InvalidTransitionError,
    LocalLocation,
    LocationRole,
    LocationStatus,
    ManifestNotFoundError,
    ManifestSyncError,
    RevisionConflictError,
    StorageSpec,
    VolumeStatus,
)

ACQUISITION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_ACQUISITION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
CREATED_AT = datetime.datetime(2026, 7, 29, 18, 30, tzinfo=datetime.UTC)


def _manifest() -> AcquisitionManifest:
    return AcquisitionManifest(
        id=ACQUISITION_ID,
        instrument="exaspim-1",
        origin=AcquisitionOrigin(host="controller-1", operator="operator"),
        created_at=CREATED_AT,
        storage=StorageSpec(path=PurePosixPath("experiment/run")),
        bench_snapshot={},
        hardware_snapshot={},
        volumes=[AcquisitionVolume(task="task-a", profile="488")],
    )


def _catalog(tmp_path: Path, backend: FileCatalogBackend | None = None) -> Catalog:
    return Catalog(
        backend or FileCatalogBackend(tmp_path / "catalog"),
        resolve_root=lambda _spec: tmp_path / "acquisition",
    )


async def test_file_catalog_creates_and_reads_manifest_json(tmp_path) -> None:
    backend = FileCatalogBackend(tmp_path / "catalog")
    catalog = _catalog(tmp_path, backend)

    created = await catalog.create(_manifest())

    assert await catalog.get(ACQUISITION_ID) == created
    path = backend.manifest_path(ACQUISITION_ID)
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["id"] == str(ACQUISITION_ID)
    assert payload["started_at"] is None
    assert payload["failure"] is None


async def test_file_catalog_allows_independent_acquisitions_during_a_write(monkeypatch, tmp_path) -> None:
    backend = FileCatalogBackend(tmp_path / "catalog")
    writing = threading.Event()
    release = threading.Event()
    original_write = backend._write_atomic

    def delayed_write(path: Path, manifest: AcquisitionManifest) -> None:
        if manifest.id == ACQUISITION_ID:
            writing.set()
            if not release.wait(timeout=5):
                raise TimeoutError
        original_write(path, manifest)

    monkeypatch.setattr(backend, "_write_atomic", delayed_write)
    first_create = asyncio.create_task(backend.create(_manifest()))
    try:
        assert await asyncio.to_thread(writing.wait, 5)
        other = _manifest().model_copy(update={"id": OTHER_ACQUISITION_ID})
        async with asyncio.timeout(1):
            assert await backend.create(other)
            assert await backend.get(OTHER_ACQUISITION_ID) == other
    finally:
        release.set()
        await first_create


async def test_catalog_updates_different_acquisitions_concurrently(monkeypatch, tmp_path) -> None:
    backend = FileCatalogBackend(tmp_path / "catalog")
    catalog = Catalog(backend, resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix())
    first = _manifest()
    other = _manifest().model_copy(
        update={
            "id": OTHER_ACQUISITION_ID,
            "storage": StorageSpec(path=PurePosixPath("experiment/other")),
        }
    )
    await catalog.create(first)
    await catalog.create(other)

    updating = asyncio.Event()
    release = asyncio.Event()
    original_compare_and_swap = backend.compare_and_swap

    async def delayed_compare_and_swap(
        manifest: AcquisitionManifest,
        *,
        expected_revision: int,
    ) -> bool:
        if manifest.id == ACQUISITION_ID:
            updating.set()
            await release.wait()
        return await original_compare_and_swap(manifest, expected_revision=expected_revision)

    monkeypatch.setattr(backend, "compare_and_swap", delayed_compare_and_swap)
    first_update = asyncio.create_task(catalog.start_acquisition(ACQUISITION_ID))
    try:
        await updating.wait()
        async with asyncio.timeout(1):
            updated = await catalog.start_acquisition(OTHER_ACQUISITION_ID)
        assert updated.revision == 2
    finally:
        release.set()
        await first_update


async def test_lifecycle_updates_sync_the_acquisition_root_manifest(tmp_path) -> None:
    acquisition_root = tmp_path / "acquisition"
    catalog = _catalog(tmp_path)

    await catalog.create(_manifest())
    await catalog.start_acquisition(ACQUISITION_ID)

    persisted = AcquisitionManifest.model_validate_json((acquisition_root / "manifest.json").read_text())
    assert persisted.revision == 2


async def test_failed_manifest_sync_keeps_indexed_revision_recoverable(tmp_path) -> None:
    backend = FileCatalogBackend(tmp_path / "catalog")
    destination = tmp_path / "available"

    def unavailable(_spec: StorageSpec) -> Path:
        raise OSError("destination unavailable")

    catalog = Catalog(backend, resolve_root=unavailable)

    with pytest.raises(ManifestSyncError, match="was indexed"):
        await catalog.create(_manifest())

    assert (await catalog.get(ACQUISITION_ID)).revision == 1
    recovered = Catalog(backend, resolve_root=lambda _spec: destination)
    await recovered.sync_manifest(ACQUISITION_ID)
    persisted = AcquisitionManifest.model_validate_json((destination / "manifest.json").read_text())
    assert persisted == _manifest()


async def test_catalog_rejects_a_noninitial_revision_on_create(tmp_path) -> None:
    catalog = _catalog(tmp_path)

    with pytest.raises(RevisionConflictError, match="must have revision 1"):
        await catalog.create(_manifest().model_copy(update={"revision": 2}))


async def test_catalog_enforces_lifecycle_transitions(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    await catalog.create(_manifest())
    await catalog.start_acquisition(ACQUISITION_ID)
    completed = await catalog.fail_acquisition(
        ACQUISITION_ID,
        AcquisitionFailure(kind="WriterError", message="upload failed"),
    )

    assert completed.status is AcquisitionStatus.FAILED
    assert completed.failure is not None
    with pytest.raises(InvalidTransitionError):
        await catalog.start_acquisition(ACQUISITION_ID)


async def test_volume_lifecycle_methods_commit_dataset_completion_atomically(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    await catalog.create(_manifest())
    await catalog.start_acquisition(ACQUISITION_ID)
    await catalog.start_volume(ACQUISITION_ID, task="task-a", profile="488")
    writing = LocalLocation(
        role=LocationRole.DESTINATION,
        status=LocationStatus.WRITING,
        host="camera-1",
        path="/data/green.ome.zarr",
    )
    registered = await catalog.register_datasets(
        ACQUISITION_ID,
        task="task-a",
        profile="488",
        locations={"green": writing},
    )

    completed = await catalog.complete_volume(ACQUISITION_ID, task="task-a", profile="488")

    dataset = completed.volumes[0].datasets["green"]
    assert completed.revision == registered.revision + 1
    assert completed.volumes[0].status is VolumeStatus.COMPLETED
    assert dataset.status is DatasetStatus.COMPLETED
    assert dataset.locations[0].status is LocationStatus.AVAILABLE


async def test_cancellation_terminalizes_running_and_pending_volumes(tmp_path) -> None:
    catalog = _catalog(tmp_path)
    manifest = _manifest().model_copy(
        update={
            "volumes": [
                AcquisitionVolume(task="task-a", profile="488"),
                AcquisitionVolume(task="task-b", profile="488"),
            ]
        }
    )
    await catalog.create(manifest)
    await catalog.start_acquisition(ACQUISITION_ID)
    await catalog.start_volume(ACQUISITION_ID, task="task-a", profile="488")

    cancelled = await catalog.cancel_acquisition(ACQUISITION_ID)

    assert cancelled.status is AcquisitionStatus.CANCELLED
    assert [volume.status for volume in cancelled.volumes] == [
        VolumeStatus.CANCELLED,
        VolumeStatus.CANCELLED,
    ]


async def test_archive_removes_manifest_from_active_catalog(tmp_path) -> None:
    backend = FileCatalogBackend(tmp_path / "catalog")
    catalog = _catalog(tmp_path, backend)
    await catalog.create(_manifest())

    await catalog.archive(ACQUISITION_ID)

    assert await catalog.list_manifests() == []
    assert (tmp_path / "catalog" / ".archive" / str(ACQUISITION_ID) / "manifest.json").is_file()
    with pytest.raises(ManifestNotFoundError):
        await catalog.get(ACQUISITION_ID)

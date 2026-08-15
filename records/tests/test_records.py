import datetime
import logging
from pathlib import Path, PurePosixPath
from uuid import UUID

import pytest
from vxl_records import (
    AcquisitionManifest,
    AcquisitionOrigin,
    AcquisitionStatus,
    AcquisitionVolume,
    LegacyImportError,
    ManifestNotFoundError,
    SQLiteRecords,
    StorageSpec,
)

CREATED_AT = datetime.datetime(2025, 8, 12, 12, tzinfo=datetime.UTC)
ACQUISITION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _manifest(
    acquisition_id: UUID = ACQUISITION_ID,
    *,
    instrument: str = "exaspim-1",
) -> AcquisitionManifest:
    return AcquisitionManifest(
        id=acquisition_id,
        instrument=instrument,
        origin=AcquisitionOrigin(host="controller-1", operator="operator"),
        created_at=CREATED_AT,
        storage=StorageSpec(path=PurePosixPath(f"runs/{acquisition_id}")),
        state_snapshot={},
        hardware_snapshot={},
        volumes=[AcquisitionVolume(task="task-a", profile="488")],
    )


def _records(tmp_path: Path) -> SQLiteRecords:
    return SQLiteRecords(
        tmp_path / "records.sqlite3",
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
    )


async def test_acquisition_lifecycle_persists_revisions_and_portable_projection(tmp_path: Path) -> None:
    records = _records(tmp_path)
    created = await records.acquisitions.create(_manifest())
    running = await records.acquisitions.start_acquisition(created.id)
    completed = await records.acquisitions.complete_acquisition(created.id)

    reopened = _records(tmp_path)
    persisted = await reopened.acquisitions.get(created.id)
    projection = tmp_path / "data" / created.storage.path.as_posix() / "manifest.json"

    assert [created.revision, running.revision, completed.revision] == [1, 2, 3]
    assert persisted == completed
    assert persisted.status is AcquisitionStatus.COMPLETED
    assert AcquisitionManifest.model_validate_json(projection.read_text(encoding="utf-8")) == persisted


async def test_legacy_import_is_idempotent_and_rolls_back_on_conflict(tmp_path: Path) -> None:
    records = _records(tmp_path)
    legacy_root = tmp_path / "legacy"
    existing = _manifest()
    existing_dir = legacy_root / str(existing.id)
    existing_dir.mkdir(parents=True)
    existing_path = existing_dir / "manifest.json"
    existing_path.write_text(existing.model_dump_json(), encoding="utf-8")

    first = await records.acquisitions.import_legacy_file_catalog(legacy_root)
    repeated = await records.acquisitions.import_legacy_file_catalog(legacy_root)

    new = _manifest(UUID("00000000-0000-4000-8000-000000000001"))
    new_dir = legacy_root / str(new.id)
    new_dir.mkdir()
    (new_dir / "manifest.json").write_text(new.model_dump_json(), encoding="utf-8")
    existing_path.write_text(
        existing.model_copy(update={"instrument": "conflicting"}).model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(LegacyImportError, match="conflicts"):
        await records.acquisitions.import_legacy_file_catalog(legacy_root)
    with pytest.raises(ManifestNotFoundError):
        await records.acquisitions.get(new.id)

    assert (first.imported, first.unchanged) == (1, 0)
    assert (repeated.imported, repeated.unchanged) == (0, 1)
    assert existing_path.is_file()


async def test_log_journal_orders_entries_and_bounds_an_acquisition_window(tmp_path: Path) -> None:
    records = _records(tmp_path)
    acquisition = await records.acquisitions.create(_manifest())
    before = await records.logs.append(
        emitted_at=CREATED_AT,
        level=20,
        logger="voxel",
        message="before",
    )
    start = await records.logs.open_acquisition_window(acquisition.id)
    first = await records.logs.append(
        emitted_at=CREATED_AT,
        level=20,
        logger="voxel",
        message="first",
    )
    second = await records.logs.append(
        emitted_at=CREATED_AT,
        level=30,
        logger="rigup",
        message="second",
        node_id="camera-node",
    )
    end = await records.logs.close_acquisition_window(acquisition.id)
    after = await records.logs.append(
        emitted_at=CREATED_AT,
        level=20,
        logger="voxel",
        message="after",
    )

    entries = await records.logs.for_acquisition(acquisition.id)

    assert [before.seq, first.seq, second.seq, after.seq] == [1, 2, 3, 4]
    assert (start, end) == (before.seq, second.seq)
    assert entries == [first, second]


async def test_log_capture_persists_structured_records_before_publishing(tmp_path: Path) -> None:
    records = _records(tmp_path)
    committed = []
    teardown = records.logs.subscribe(committed.append)
    logger = logging.getLogger("vxl.test.capture")
    logger.setLevel(logging.DEBUG)

    try:
        async with records.logs.capture():
            logger.error(
                "Device failed",
                exc_info=ValueError("camera unavailable"),
                extra={"node_id": "camera-node"},
            )
            await records.logs.mark()
    finally:
        teardown()

    entries = [entry for entry in await records.logs.tail() if entry.logger == logger.name]
    assert committed == entries
    assert len(entries) == 1
    assert entries[0].level == logging.ERROR
    assert entries[0].node_id == "camera-node"
    assert entries[0].exception is not None
    assert entries[0].exception.kind == "ValueError"
    assert "camera unavailable" in entries[0].exception.traceback


async def test_log_capture_reports_overflow_before_releasing_a_barrier(tmp_path: Path) -> None:
    records = SQLiteRecords(
        tmp_path / "records.sqlite3",
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
        log_queue_size=1,
    )
    logger = logging.getLogger("vxl.test.overflow")
    logger.setLevel(logging.INFO)

    async with records.logs.capture():
        logger.info("admitted")
        logger.info("dropped-one")
        logger.info("dropped-two")
        boundary = await records.logs.mark()

    entries = await records.logs.tail()
    assert boundary == 2
    assert [entry.message for entry in entries] == [
        "admitted",
        "Dropped 2 log record(s) because the capture queue was full",
    ]
    assert entries[1].attributes == {"dropped_count": 2}

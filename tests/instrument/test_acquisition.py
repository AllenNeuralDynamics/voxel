import asyncio
from pathlib import Path, PurePosixPath

import pytest
from vxl_records import (
    AcquisitionStatus,
    DatasetStatus,
    LocalLocation,
    LocationRole,
    LocationStatus,
    SQLiteRecords,
    StorageSpec,
    VolumeStatus,
)

from vxl.devices.camera import CaptureState
from vxl.instrument import AcquisitionMode, ActiveAcquisitionState, Instrument
from vxl.instrument.config import TaskPatch
from vxl.instrument.models import AcquisitionRequest


class _Writer:
    def __init__(self, root: Path, *, close_error: bool = False) -> None:
        self.uid = "camera_1"
        self._root = root
        self._close_error = close_error
        self._closing = False
        self.released = False

    async def check_writable(self, _storage: StorageSpec) -> None:
        return

    async def open_stack(self, *, storage: StorageSpec, subpath: PurePosixPath, **_kwargs: object) -> LocalLocation:
        target = self._root / storage.path.as_posix() / f"{subpath.as_posix()}.ome.zarr"
        return LocalLocation(
            role=LocationRole.DESTINATION,
            status=LocationStatus.WRITING,
            host="camera-1",
            path=str(target),
        )

    async def begin_batch(self, _num_frames: int) -> None:
        return

    async def capture_state(self) -> CaptureState:
        return CaptureState.CLOSED if self._closing else CaptureState.DONE

    async def close_stack(self) -> None:
        if self._close_error:
            raise RuntimeError("writer close failed")
        self._closing = True

    async def release_writer(self) -> None:
        self.released = True


@pytest.fixture
async def writer(opened_instrument: Instrument, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Writer:
    instrument = opened_instrument
    writer = _Writer(tmp_path / "data")
    camera = instrument._hal.cameras["camera_1"]
    for name in ("check_writable", "open_stack", "begin_batch", "capture_state", "close_stack", "release_writer"):
        monkeypatch.setattr(camera, name, getattr(writer, name))
    await instrument.add_tasks([(0, 0)])
    task_id = next(iter(instrument.state.value.tasks))
    await instrument.update_tasks({task_id: TaskPatch(start=0, end=0, profile_ids=["single_gfp"])})
    return writer


async def test_acquisition_manifest_tracks_completed_dataset(
    opened_instrument: Instrument, records: SQLiteRecords, writer: _Writer, tmp_path: Path
) -> None:
    instrument = opened_instrument
    catalog = records.acquisitions
    storage = StorageSpec(path=PurePosixPath("run"))
    states: list[ActiveAcquisitionState | None] = []
    instrument.acquisition.subscribe(states.append)
    started = await instrument.start_acquisition(AcquisitionRequest(storage=storage, operator="operator"))
    await asyncio.wait_for(instrument.wait_acquisition(), timeout=5)

    persisted = await catalog.get(started.manifest.id)
    dataset = persisted.volumes[0].datasets["gfp"]
    assert started.manifest.status is AcquisitionStatus.RUNNING
    assert started.progress.task == next(iter(instrument.state.value.tasks))
    assert started.progress.profile == "single_gfp"
    assert started.progress.frames_captured == 0
    assert started.progress.frames_total == 1
    assert instrument.acquisition.value is None
    assert states[-1] is None
    assert any(
        state is not None
        and state.manifest.status is AcquisitionStatus.COMPLETED
        and state.progress.frames_captured == state.progress.frames_total
        for state in states
    )
    assert persisted.status is AcquisitionStatus.COMPLETED
    assert persisted.volumes[0].status is VolumeStatus.COMPLETED
    assert dataset.status is DatasetStatus.COMPLETED
    location = dataset.locations[0]
    assert isinstance(location, LocalLocation)
    assert location.status is LocationStatus.AVAILABLE
    assert location.path == str(tmp_path / "data/run/tasks/0001/single_gfp/gfp.ome.zarr")
    assert persisted.state_snapshot == instrument.state.value.model_dump(mode="json")
    assert (tmp_path / "data/run/manifest.json").is_file()
    assert not (tmp_path / "data/run/record.json").exists()
    assert writer.released
    assert instrument.mode.value is AcquisitionMode.IDLE


async def test_writer_close_failure_marks_dataset_and_acquisition_failed(
    opened_instrument: Instrument, records: SQLiteRecords, writer: _Writer
) -> None:
    instrument = opened_instrument
    catalog = records.acquisitions
    storage = StorageSpec(path=PurePosixPath("run"))
    writer._close_error = True

    started = await instrument.start_acquisition(AcquisitionRequest(storage=storage, operator="operator"))
    await asyncio.wait_for(instrument.wait_acquisition(), timeout=5)

    persisted = await catalog.get(started.manifest.id)
    dataset = persisted.volumes[0].datasets["gfp"]
    assert persisted.status is AcquisitionStatus.FAILED
    assert persisted.failure is not None
    assert persisted.volumes[0].status is VolumeStatus.FAILED
    assert dataset.status is DatasetStatus.PARTIAL
    assert dataset.locations[0].status is LocationStatus.FAILED
    assert writer.released
    assert instrument.mode.value is AcquisitionMode.IDLE

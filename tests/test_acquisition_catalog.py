import asyncio
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, cast

from vxl_records import (
    AcquisitionCatalog,
    AcquisitionStatus,
    AcquisitionVolume,
    DatasetStatus,
    LocalLocation,
    LocationRole,
    LocationStatus,
    SQLiteRecords,
    StorageSpec,
    VolumeStatus,
)

from vxl.devices.camera import CaptureState
from vxl.instrument import AcquisitionMode, ActiveAcquisitionState, Instrument, InstrumentConfig, InstrumentState
from vxl.instrument.config import AcquisitionTask
from vxl.instrument.core import AcquisitionRequest, Channel
from vxl.system import System
from vxlib import Cell, load_yaml

TEMPLATE = Path(__file__).parents[1] / "src/vxl/station/templates/builtins/simulated-local.voxel.yaml"


class _FakeCamera:
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

    async def reset_preview_stream(self) -> str:
        return "preview-source"


class _FakeLaser:
    async def call(self, _command: str) -> None:
        return


class _FakeAxis:
    async def move_abs(self, _position: float, *, wait: bool) -> None:
        del wait

    async def configure_ttl_stepper(self, _config: object) -> None:
        return

    async def queue_relative_move(self, _distance: float) -> None:
        return

    async def reset_ttl_stepper(self) -> None:
        return


def _instrument(tmp_path: Path, *, close_error: bool = False) -> tuple[Instrument, AcquisitionCatalog, StorageSpec]:
    config = load_yaml(TEMPLATE, InstrumentConfig)
    task = AcquisitionTask(x=0, y=0, start=0, end=0, profile_ids=["single_gfp"])
    state = InstrumentState(**config.default.model_dump()).model_copy(update={"tasks": {"task-a": task}})
    records = SQLiteRecords(
        tmp_path / "records.sqlite3",
        resolve_root=lambda spec: tmp_path / "data" / spec.path.as_posix(),
    )
    catalog = records.acquisitions
    camera = _FakeCamera(tmp_path / "data", close_error=close_error)
    axis = _FakeAxis()
    instrument = cast("Any", object.__new__(Instrument))
    instrument._store = SimpleNamespace(value=state, home=tmp_path / "scope.voxel")
    instrument._records = records
    instrument._system = System(store=tmp_path / "data", scratch=tmp_path / "scratch", remotes={})
    instrument._hal = SimpleNamespace(
        cameras={"camera_1": camera},
        config=config.hal,
        stage=SimpleNamespace(x=axis, y=axis, z=axis, scanning_axis=axis),
    )
    instrument._channels = {"gfp": Channel(uid="gfp", camera=cast("Any", camera), laser=cast("Any", _FakeLaser()))}
    instrument._active_profile_id = Cell("single_gfp")
    instrument._preview_revision = Cell(0)
    instrument._preview_source_ids = {}
    instrument._accept_preview = False
    instrument._routing_targets = Cell({})
    instrument._mode = Cell(AcquisitionMode.IDLE)
    instrument._acquisition = Cell(None)
    instrument._lock = asyncio.Lock()
    instrument._acq_task = None
    plan = [AcquisitionVolume(task="task-a", profile="single_gfp")]
    instrument._generate_plan = lambda _task_ids: plan

    async def no_op(*_args: object, **_kwargs: object) -> None:
        return

    instrument._apply_profile = no_op
    instrument._move_optical_routes = no_op
    instrument._start_signal_generators = no_op
    instrument._stop_signal_generators = no_op
    return instrument, catalog, StorageSpec(path=PurePosixPath("run"))


async def test_acquisition_manifest_tracks_completed_dataset(tmp_path: Path) -> None:
    instrument, catalog, storage = _instrument(tmp_path)
    states: list[ActiveAcquisitionState | None] = []
    instrument.acquisition.subscribe(states.append)
    started = await instrument.start_acquisition(AcquisitionRequest(storage=storage, operator="operator"))
    await instrument.wait_acquisition()

    persisted = await catalog.get(started.manifest.id)
    dataset = persisted.volumes[0].datasets["gfp"]
    assert started.manifest.status is AcquisitionStatus.RUNNING
    assert started.progress.task == "task-a"
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


async def test_writer_close_failure_marks_dataset_and_acquisition_failed(tmp_path: Path) -> None:
    instrument, catalog, storage = _instrument(tmp_path, close_error=True)

    started = await instrument.start_acquisition(AcquisitionRequest(storage=storage, operator="operator"))
    await instrument.wait_acquisition()

    persisted = await catalog.get(started.manifest.id)
    dataset = persisted.volumes[0].datasets["gfp"]
    assert persisted.status is AcquisitionStatus.FAILED
    assert persisted.failure is not None
    assert persisted.volumes[0].status is VolumeStatus.FAILED
    assert dataset.status is DatasetStatus.PARTIAL
    assert dataset.locations[0].status is LocationStatus.FAILED

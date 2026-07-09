import asyncio
import logging
import shutil
import time
from abc import abstractmethod
from contextlib import suppress
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal, Self, cast

import numpy as np
from cloudpathlib import S3Path
from ome_zarr_writer import (
    DirectS3,
    Local,
    OMEZarrWriter,
    StagedS3,
    Storage,
    UIVec3D,
    UVec3D,
    WriterConfig,
    WriterSettings,
)
from ome_zarr_writer.writer import BatchMetrics
from pydantic import BaseModel, model_validator
from vxlib.vec import IVec2D, Vec2D

from rigup import Device, DeviceController, describe, enumerated, enumerated_int, numeric
from vxl.camera.preview import (
    PreviewConfig,
    PreviewFrame,
    PreviewGenerator,
    PreviewLevels,
    PreviewViewport,
)
from vxl.device import DeviceType
from vxl.system import System
from vxlib import Dtype, SchemaModel

log = logging.getLogger(__name__)


class RemoteTarget(SchemaModel):
    """An S3 destination: which configured store (a key into ``System.remotes``), which root,
    and whether to stage. The node resolves ``store`` to a connection from its own registry."""

    store: str  # key into System.remotes
    root: str
    stage: bool = False  # write to local scratch first, then upload


class StorageSpec(SchemaModel):
    """Where a camera writes, specified logically by the controller. The node resolves it:
    ``remote is None`` → the node's local store; else the S3 root named by ``remote``.
    Absolute paths and the scratch location are the node's to fill, never the controller's."""

    path: PurePosixPath  # relative run base, e.g. "exp42/2024-ts" (sub-structure is passed as a subpath)
    remote: RemoteTarget | None = None  # None → node-local store; else an S3 destination

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.path.is_absolute() or ".." in self.path.parts:
            raise ValueError("path must be relative and stay under the root")
        return self

    def resolve(self, subpath: PurePosixPath | None = None) -> Storage:
        """Resolve to a concrete omezarr :class:`Storage` at ``<base>/<subpath>`` on this machine:
        :class:`Local` for a node-local write, else :class:`DirectS3`/:class:`StagedS3` with the
        connection looked up from :attr:`System.remotes`. No ``.ome.zarr`` — the writer names the
        dataset; navigate below the returned location with ``target / ...``."""
        if subpath is None:
            subpath = PurePosixPath()
        relpath = self.path / subpath
        if self.remote is None:
            return Local(target=System().store / relpath)
        remotes = System().remotes
        if self.remote.store not in remotes:
            raise KeyError(f"unknown remote store '{self.remote.store}'; configured: {sorted(remotes)}")
        store = remotes[self.remote.store]  # Remote is-a S3Store
        target = S3Path(f"s3://{self.remote.root}") / relpath.as_posix()
        if self.remote.stage:
            return StagedS3(scratch=System().scratch / relpath, target=target, store=store)
        return DirectS3(target=target, store=store)


class StorageStatus(SchemaModel):
    """A node's write-access result for a `Storage` root (preflight). ``free_bytes`` is -1 when
    capacity is unknown (e.g. an S3 root)."""

    host: str
    root: str
    free_bytes: int


class DatasetRef(SchemaModel):
    """Control-owned pointer to one written OME-Zarr dataset — the content of ``<channel>.ref.json``.
    Self-describing (carries geometry), not a bare path."""

    host: str
    target: str
    staged: bool
    dtype: Dtype
    shape: UIVec3D  # z=num_frames, y, x
    voxel_size: UVec3D  # z=z_step, y, x (sample-space µm)


class IntRange(BaseModel):
    """Integer range with min, max, and step."""

    min: int
    max: int
    step: int = 1


class ROIGrid(BaseModel):
    """Hardware constraints for sensor ROI, one range per axis.

    Each axis describes valid sizes (width/height) with min, max, and step.
    Offset constraints are derived: min=0, max=axis.max - snapped_size, same step.
    """

    h: IntRange  # horizontal: valid widths
    v: IntRange  # vertical: valid heights


class SensorROI(BaseModel):
    """Region of interest on the camera sensor, in physical sensor pixels (pre-binning).

    All coordinates are in the unbinned sensor pixel space. FOV depends only on
    (x, y, w, h) and the camera's pixel_size_um — binning is independent.
    """

    x: int = 0
    y: int = 0
    w: int
    h: int

    def snap(self, grid: ROIGrid) -> "SensorROI":
        """Return a new SensorROI clamped and aligned to the given grid.

        Snaps size first, then derives offset bounds from the snapped size.
        """

        def _snap(value: int, r: IntRange) -> int:
            value = max(r.min, min(value, r.max))
            remainder = (value - r.min) % r.step
            if remainder != 0:
                value = value - remainder if remainder < r.step / 2 else value + (r.step - remainder)
            return min(value, r.max)

        w = _snap(self.w, grid.h)
        h = _snap(self.h, grid.v)
        x = _snap(self.x, IntRange(min=0, max=grid.h.max - w, step=grid.h.step))
        y = _snap(self.y, IntRange(min=0, max=grid.v.max - h, step=grid.v.step))
        return SensorROI(x=x, y=y, w=w, h=h)


class TriggerMode(StrEnum):
    OFF = "off"
    ON = "on"


class TriggerPolarity(StrEnum):
    RISING_EDGE = "rising"
    FALLING_EDGE = "falling"


class StreamInfo(SchemaModel):
    frame_index: int
    input_buffer_size: int
    output_buffer_size: int
    dropped_frames: int
    frame_rate_fps: float
    data_rate_mbs: float
    payload_mbs: float | None = None


PixelFormat = Literal["MONO8", "MONO10", "MONO12", "MONO14", "MONO16"]

PIXEL_FMT_TO_DTYPE: dict[PixelFormat, Dtype] = {
    "MONO8": Dtype.UINT8,
    "MONO10": Dtype.UINT16,
    "MONO12": Dtype.UINT16,
    "MONO14": Dtype.UINT16,
    "MONO16": Dtype.UINT16,
}

BINNING_OPTIONS = [1, 2, 4, 8]


class CaptureState(StrEnum):
    IDLE = "IDLE"
    COLLECTING = "COLLECTING"
    DONE = "DONE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class CameraMode(StrEnum):
    IDLE = "IDLE"
    PREVIEW = "PREVIEW"
    ACQUISITION = "ACQUISITION"


# Ring depth: at least 2 (so collect overlaps downsample/flush) up to this cap (coordination +
# cache pressure outweigh gains beyond it). Sized within these bounds from the camera's RAM share.
MIN_WRITER_SLOTS = 2
MAX_WRITER_SLOTS = 5


class CameraController(DeviceController["Camera"]):
    def __init__(self, device: "Camera", stream_interval: float = 0.5):
        super().__init__(device, stream_interval=stream_interval)
        self._mode = CameraMode.IDLE
        self._preview_task: asyncio.Task | None = None
        self._frame_idx = 0
        self._previewer = PreviewGenerator(
            frame_sink=self._on_preview_frame,
            view_sink=self._on_preview_view,
            uid=device.uid,
        )
        self._writer: OMEZarrWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._task_kind: Literal["batch", "close"] | None = None
        self._preview_publishing = False
        self._publish_task: asyncio.Task | None = None
        System.Ram.reserve(self.device.uid, weight=1.0)

    async def close(self) -> None:
        self._preview_publishing = False
        self._publish_fn = None
        self._previewer.shutdown()
        if self._writer is not None:  # free the reusable ring (its slots' workers + shared memory)
            await self._run_sync(self._writer.close)
            self._writer = None
        System.Ram.release(self.device.uid)
        await super().close()

    @property
    @describe(label="RAM Budget", units="bytes", stream=True)
    def ram_budget_bytes(self) -> int:
        """Current RAM share for this camera from the host RAM budget."""
        return System.Ram.reserved(self.device.uid)

    @property
    @describe(label="Camera Mode", stream=True)
    def mode(self) -> CameraMode:
        return self._mode

    @property
    @describe(label="Writer Metrics", stream=True)
    def writer_metrics(self) -> list[BatchMetrics]:
        return self._writer.batches if self._writer else []

    def _on_preview_frame(self, frame: PreviewFrame) -> None:
        # Publish live frames (preview/acquisition); while idle, only a one-off reprocessed frame.
        if self._mode is CameraMode.IDLE and not self._preview_publishing:
            return
        if self._publish_task is not None and not self._publish_task.done():
            return
        self._publish_task = asyncio.create_task(self._publish_overview(frame))

    async def _publish_overview(self, frame: PreviewFrame) -> None:
        with suppress(RuntimeError):
            await self.publish("preview", frame.pack())

    async def _on_preview_view(self, packed: bytes) -> None:
        if self._mode is CameraMode.IDLE and not self._preview_publishing:
            return
        with suppress(RuntimeError):
            await self.publish("preview_view", packed)

    @describe(label="Update Preview Viewport")
    async def update_preview_viewport(self, viewport: PreviewViewport):
        if self._mode is not CameraMode.IDLE:
            self._previewer.viewport = viewport
        else:
            self._preview_publishing = True
            await self._previewer.reprocess_viewport(viewport)
            self._preview_publishing = False

    @describe(label="Update Preview Levels")
    async def update_preview_levels(self, levels: PreviewLevels):
        self._previewer.levels = levels
        if self._mode is CameraMode.IDLE:
            self._preview_publishing = True
            await self._previewer.reprocess()
            self._preview_publishing = False

    @describe(label="Clear Preview Cache")
    async def clear_preview_cache(self) -> None:
        """Clear cached frame. Called on profile change."""
        self._previewer.clear_cache()

    @describe(label="Update Preview Colormap")
    async def update_preview_colormap(self, colormap: str | None) -> None:
        self._previewer.colormap = colormap
        if self._mode is CameraMode.IDLE:
            self._preview_publishing = True
            await self._previewer.reprocess()
            self._preview_publishing = False

    @describe(label="Auto Level")
    async def auto_level(self, percentile: float = 1.0) -> None:
        """Set preview levels by percentile-clipping the latest overview histogram (no-op before any frame)."""
        if (histogram := self._previewer.last_histogram) is not None:
            await self.update_preview_levels(PreviewLevels.from_histogram(histogram, percentile))

    @property
    @describe(label="Preview Config", stream=True)
    def preview_config(self) -> PreviewConfig:
        return PreviewConfig(
            viewport=self._previewer.viewport,
            levels=self._previewer.levels,
            colormap=self._previewer.colormap,
        )

    @describe(label="Get Preview Config")
    async def get_preview_config(self) -> PreviewConfig:
        """Deprecated — use preview_config property instead."""
        return self.preview_config

    @describe(label="Start Preview")
    async def start_preview(
        self,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start preview mode. Returns topic name where frames will be published."""
        if self._mode != CameraMode.IDLE:
            raise RuntimeError(f"Cannot start preview: camera in {self._mode} mode")

        # start() lazily allocates the buffer, configures the trigger, and begins (frame_count=None → infinite).
        await self._run_sync(
            lambda: self.device.start(frame_count=None, trigger_mode=trigger_mode, trigger_polarity=trigger_polarity)
        )

        self._mode = CameraMode.PREVIEW
        self._frame_idx = 0
        self._preview_task = asyncio.create_task(self._preview_loop())

        return "preview"

    async def _preview_loop(self):
        try:
            while self._mode == CameraMode.PREVIEW:
                frame = await self._run_sync(self.device.grab_frame)
                await self._previewer.new_frame(frame, idx=self._frame_idx)
                self._frame_idx += 1
        except asyncio.CancelledError:
            pass
        except Exception:
            self.log.exception("Preview loop error")
            self._mode = CameraMode.IDLE

    @describe(label="Stop Preview")
    async def stop_preview(self):
        if self._mode != CameraMode.PREVIEW:
            return

        self._mode = CameraMode.IDLE
        self._preview_publishing = False
        self._previewer.cancel_view_task()
        if self._preview_task:
            await self._preview_task
            self._preview_task = None
        await self._run_sync(self.device.stop)
        await self._run_sync(self.device.free_buffer)

    @describe(label="Check Writable")
    async def check_writable(self, storage: StorageSpec) -> StorageStatus:
        """Resolve ``storage`` on this node and prove write access with a round-trip marker write.

        The acquisition preflight (before any task): raises with a clear reason if the destination
        is unreachable or not writable, so the run aborts before any stage motion or capture.
        """

        def _check() -> StorageStatus:
            dest = storage.resolve()
            root = dest.target  # client-bound path for S3, plain path for local
            root.mkdir(parents=True, exist_ok=True)
            marker = root / f".voxel_write_check-{self.device.uid}"
            marker.write_text(self.device.uid)  # raises on missing creds / no permission / unreachable
            marker.unlink(missing_ok=True)
            free = shutil.disk_usage(root).free if isinstance(root, Path) else -1
            return StorageStatus(host=System.hostname(), root=str(root), free_bytes=free)

        return await self._run_sync(_check)

    @describe(label="Open Stack")
    async def open_stack(
        self,
        *,
        num_frames: int,
        z_step: float,
        magnification: float,
        storage: StorageSpec,
        subpath: PurePosixPath,
        settings: WriterSettings,
    ) -> DatasetRef:
        """Prepare the camera + writer for a stack and return a pointer to its dataset.

        ``storage`` is the run's logical destination and ``subpath`` the dataset's relative location
        under it (e.g. ``task/profile/channel``); the node resolves ``storage.resolve(subpath)`` and
        the writer names it ``<subpath>.ome.zarr``. ``num_frames``/``z_step`` are the volume's
        geometry; ``magnification`` converts the sensor-space ``effective_pixel_size_um`` into the
        sample-space lateral voxel size. ``settings`` are the broadcast output-format knobs. Returns a
        :class:`DatasetRef` (control persists it as ``<channel>.ref.json``). The trigger is configured
        per-batch in ``begin_batch``.
        """
        if self._mode != CameraMode.IDLE:  # a stack already open (or previewing) → mode is not IDLE
            raise RuntimeError(f"Cannot open stack: camera in {self._mode} mode")

        self._mode = CameraMode.ACQUISITION
        self._frame_idx = 0
        self._task = None
        self._task_kind = None

        # Allocate buffers eagerly (after ROI is set), so every batch's start() is fast.
        _t = time.perf_counter()
        await self._run_sync(self.device.allocate_buffer)
        log.info("allocate_buffer for %s took %.1fs", self.device.uid, time.perf_counter() - _t)

        # Resolve the logical StorageSpec to a concrete omezarr Storage, then build the writer config:
        # the broadcast `settings` (knobs) + this camera's geometry (frame size, voxel size from
        # z_step + magnification) + dtype from the device's pixel format. Where/how to write lives on
        # the Storage; the config is purely the dataset spec.
        dest = storage.resolve(subpath)
        frame = self.device.frame_size_px
        eff_px = self.device.effective_pixel_size_um(magnification)
        cfg = WriterConfig(
            **settings.model_dump(),
            volume_shape=UIVec3D(z=num_frames, y=frame.y, x=frame.x),
            voxel_size=UVec3D(z=z_step, y=eff_px.y, x=eff_px.x),
            dtype=self.device.pixel_type,
        )

        # Size the ring from this camera's RAM share. `cfg.batch_z` is policy-derived (matches the
        # engine's batch_z), so a slot holds one batch + its pyramid tail (~1/7 overhead). Refuse if
        # not even the minimum slot count fits — one slot would serialize collect against flush.
        frame_bytes = frame.y * frame.x * self.device.pixel_type.itemsize
        per_slot_bytes = int(cfg.batch_z * frame_bytes * 8 / 7)
        budget = self.ram_budget_bytes
        max_slots = budget // per_slot_bytes if per_slot_bytes else 0
        if max_slots < MIN_WRITER_SLOTS:
            raise RuntimeError(
                f"{self.device.uid}: cannot fit {MIN_WRITER_SLOTS} batch slots "
                f"({per_slot_bytes:,} B/slot, {budget:,} B RAM share). Reduce batch_z_shards, "
                f"shard_z_chunks, max_level, target_shard_gb, or ROI; or raise max_ram_fraction."
            )
        slots = min(max_slots, MAX_WRITER_SLOTS)
        if self._writer is None:  # the coordinator persists across volumes so its ring is reused
            self._writer = OMEZarrWriter(slots=slots)
        _t = time.perf_counter()
        self._writer.begin_stack(cfg, dest)  # (re)allocates the ring on the first volume; reused after
        log.info(
            "OMEZarrWriter begin_stack for %s took %.1fs (%d slots, %.2f GB ring)",
            self.device.uid,
            time.perf_counter() - _t,
            slots,
            slots * per_slot_bytes / 1e9,
        )

        log.info(
            "Stack init for %s → %s: batch_z=%d slots=%d (%.2f GB/slot, %.2f GB share)",
            self.device.uid,
            self._writer.target,
            cfg.batch_z,
            slots,
            per_slot_bytes / 1e9,
            budget / 1e9,
        )
        return DatasetRef(
            host=System.hostname(),
            target=str(self._writer.target),
            staged=isinstance(dest, StagedS3),
            dtype=cfg.dtype,
            shape=cfg.volume_shape,
            voxel_size=cfg.voxel_size,
        )

    @describe(label="Close Stack")
    async def close_stack(self) -> None:
        """Drain and close the writer in the background, then disarm the camera. Returns immediately;
        poll :meth:`capture_state` until ``CLOSED``. Draining/uploading can take a while, so it runs
        off the RPC path rather than blocking the call."""
        if self._task is not None and not self._task.done():
            raise RuntimeError("Capture task already in progress.")
        self._task = asyncio.create_task(self._close_stack())
        self._task_kind = "close"

    async def _close_stack(self) -> None:
        """Flush and close the writer, then reset the camera to a reusable IDLE state.

        The camera is always reset even if ``writer.close()`` raises (e.g. a flush error): the writer is
        dropped, the buffer freed, and the mode returned to IDLE in a ``finally``, so a close failure
        can't wedge the camera into "Stack already open" on the next run.
        """
        self._preview_publishing = False
        self._previewer.cancel_view_task()
        try:
            if self._writer is not None:
                await self._run_sync(self._writer.end_stack)  # drain the dataset; keep the ring for reuse
        finally:
            await self._run_sync(self.device.free_buffer)
            self._mode = CameraMode.IDLE
        log.info("Stack closed for %s", self.device.uid)

    @property
    @describe(label="Ready For Batch", stream=True)
    def ready_for_batch(self) -> bool:
        """Whether the writer has at least one free slot to accept the next batch.

        True when no stack is initialized, or when at least one ring-buffer slot
        is IDLE.
        """
        return self._writer is None or self._writer.ready_for_batch

    @describe(label="Begin Batch")
    async def begin_batch(
        self,
        num_frames: int,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> None:
        """Arm the trigger for ``num_frames`` frames and start grabbing them in the background.

        Waits for a free writer slot, then arms the camera before returning — so the caller can start
        the AO/triggers as soon as this resolves. Poll :meth:`capture_state` for completion; frame and
        pipeline progress stream via ``writer_metrics``. Must call ``open_stack`` first.
        """
        if self._writer is None:
            raise RuntimeError("No stack open. Call open_stack() first.")
        if self._mode != CameraMode.ACQUISITION:
            raise RuntimeError(f"Cannot capture batch: camera in {self._mode} mode")
        if self._task is not None and not self._task.done():
            raise RuntimeError("Capture task already in progress.")
        writer = self._writer
        while True:  # wait for a free ring slot before arming (a prior batch may still be flushing)
            if writer.ready_for_batch:
                break
            await asyncio.sleep(0.005)
        await self._run_sync(
            lambda: self.device.start(
                frame_count=num_frames, trigger_mode=trigger_mode, trigger_polarity=trigger_polarity
            )
        )
        self._task = asyncio.create_task(self._collect_batch(num_frames, writer))
        self._task_kind = "batch"

    async def _collect_batch(self, num_frames: int, writer: OMEZarrWriter) -> None:
        """Grab ``num_frames`` frames into the writer, then stop the camera."""
        for _ in range(num_frames):
            frame = await self._run_sync(self.device.grab_frame)
            writer.add_frame(frame)
            await self._previewer.new_frame(frame, self._frame_idx)
            self._frame_idx += 1
        await self._run_sync(self.device.stop)

    @describe(label="Capture State")
    async def capture_state(self) -> CaptureState:
        """Lifecycle of the most recent :meth:`begin_batch`/:meth:`close_stack` task. Non-mutating: the
        terminal state persists until the next task starts. Raises if the task failed."""
        task = self._task
        if task is None:
            return CaptureState.IDLE
        if not task.done():
            return CaptureState.COLLECTING if self._task_kind == "batch" else CaptureState.CLOSING
        if (exc := task.exception()) is not None:
            raise RuntimeError(f"Capture task failed: {exc}")
        return CaptureState.DONE if self._task_kind == "batch" else CaptureState.CLOSED


class Camera(Device):
    __DEVICE_TYPE__ = DeviceType.CAMERA
    __CONTROLLER_TYPE__ = CameraController

    trigger_mode: TriggerMode = TriggerMode.OFF
    trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE

    _buffer_allocated = False

    @property
    @abstractmethod
    @describe(label="Sensor Size", units="px")
    def sensor_size_px(self) -> IVec2D:
        """Get the size of the camera sensor in pixels."""

    @property
    @abstractmethod
    @describe(label="Pixel Size", units="µm", desc="The size of the camera pixel in microns.")
    def pixel_size_um(self) -> Vec2D:
        """Get the size of the camera pixel in microns."""

    @enumerated(options=list(PIXEL_FMT_TO_DTYPE.keys()))
    @abstractmethod
    @describe(label="Pixel Format", stream=True)
    def pixel_format(self) -> PixelFormat:
        """Get the pixel format of the camera."""

    @pixel_format.setter
    @abstractmethod
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel format of the camera."""

    @property
    @describe(label="Pixel Type", stream=True)
    def pixel_type(self) -> Dtype:
        """Get the pixel type of the camera."""
        return PIXEL_FMT_TO_DTYPE[cast("PixelFormat", str(self.pixel_format))]

    @enumerated_int(options=BINNING_OPTIONS)
    @abstractmethod
    @describe(label="Binning", stream=True)
    def binning(self) -> int:
        """Get the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning."""

    @binning.setter
    @abstractmethod
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera. Integer value, e.g. 2 is 2x2 binning."""

    @numeric()
    @abstractmethod
    @describe(label="Exposure Time", units="ms", stream=True)
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms."""

    @exposure_time_ms.setter
    @abstractmethod
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms."""

    @numeric()
    @abstractmethod
    @describe(label="Frame Rate", units="Hz", stream=True)
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz."""

    @frame_rate_hz.setter
    @abstractmethod
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate of the camera in Hz."""

    # ==================== Sensor ROI ====================

    @abstractmethod
    def _get_roi(self) -> SensorROI:
        """Read the current ROI from hardware in sensor pixel coordinates."""

    @abstractmethod
    def _set_roi(self, roi: SensorROI) -> None:
        """Apply ROI to hardware. Values are pre-snapped by update_roi."""

    @property
    @abstractmethod
    @describe(label="ROI Grid", stream=True)
    def roi_grid(self) -> ROIGrid:
        """Hardware constraints for the sensor ROI.

        Returns the valid size ranges (min/max/step) for each axis.
        These are dynamic — they may change with binning mode.
        """

    @property
    @describe(label="Sensor ROI", stream=True)
    def roi(self) -> SensorROI:
        """Current sensor ROI in physical sensor pixels (pre-binning)."""
        return self._get_roi()

    @describe(label="Update ROI")
    def update_roi(self, roi: SensorROI, *, snap: bool = True) -> SensorROI:
        """Set sensor ROI. Returns the actual applied ROI.

        Args:
            roi: Desired ROI in physical sensor pixels (pre-binning).
            snap: If True (default), clamp and align to hardware grid.
                  If False, raise ValueError if ROI doesn't conform.
        """
        grid = self.roi_grid
        snapped = roi.snap(grid)
        if not snap and roi != snapped:
            raise ValueError(f"ROI {roi} does not conform to grid {grid}; nearest valid ROI is {snapped}")
        self._set_roi(snapped)
        return self._get_roi()

    @describe(label="Reset ROI")
    def reset_roi(self) -> SensorROI:
        """Reset the sensor ROI to the full sensor."""
        return self.update_roi(SensorROI(w=self.sensor_size_px.x, h=self.sensor_size_px.y))

    @property
    @describe(label="Frame Size", units="px", stream=True)
    def frame_size_px(self) -> IVec2D:
        """Get the image size in pixels (post-binning frame coordinates)."""
        roi = self.roi
        b = int(self.binning)
        return IVec2D(y=roi.h // b, x=roi.w // b)

    @property
    @describe(label="Frame Size", units="MB", stream=True)
    def frame_size_mb(self) -> float:
        """Get the size of the camera image in MB."""
        return (self.frame_size_px.x * self.frame_size_px.y * self.pixel_type.itemsize) / 1_000_000

    @property
    @describe(label="Frame Area", units="µm", stream=True)
    def frame_area_um(self) -> Vec2D:
        """Get the physical frame size in micrometers."""
        roi = self.roi
        return Vec2D(
            x=roi.w * self.pixel_size_um.x,
            y=roi.h * self.pixel_size_um.y,
        )

    @property
    @abstractmethod
    @describe(label="Stream Info", stream=True)
    def stream_info(self) -> StreamInfo | None:
        """Return a dictionary of the acquisition state or None if not acquiring.

        - Frame Index - frame number of the acquisition
        - Input Buffer Size - number of free frames in buffer
        - Output Buffer Size - number of frames to grab from buffer
        - Dropped Frames - number of dropped frames
        - Data Rate [MB/s] - data rate of acquisition
        - Frame Rate [fps] - frames per second of acquisition
        """

    def effective_pixel_size_um(self, magnification: float = 1.0) -> Vec2D:
        """Physical size of each output pixel in µm, accounting for binning."""
        b = int(self.binning)
        return Vec2D(x=self.pixel_size_um.x * b, y=self.pixel_size_um.y * b) / magnification

    @abstractmethod
    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        """Configure the trigger mode of the camera."""

    @abstractmethod
    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        """Configure the trigger polarity of the camera."""

    @abstractmethod
    def _start(self, frame_count: int | None = None) -> None:
        """Begin acquiring ``frame_count`` frames (None = until stopped). Driver primitive for start()."""

    @abstractmethod
    def _allocate_buffer(self) -> None:
        """Allocate capture buffers. Driver primitive for allocate_buffer()."""

    def _free_buffer(self) -> None:
        """Release capture buffers. Override if the driver needs explicit cleanup."""

    def allocate_buffer(self) -> None:
        """Allocate capture buffers (releasing any existing first)."""
        self.free_buffer()
        self._allocate_buffer()
        self._buffer_allocated = True

    def free_buffer(self) -> None:
        """Release capture buffers."""
        self._free_buffer()
        self._buffer_allocated = False

    def start(
        self,
        frame_count: int | None = None,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> None:
        """Start the camera to acquire a certain number of frames.

        If frame number is not specified, acquires infinitely until stopped.
        Initializes the camera buffer.

        Arguments:
            frame_count: The number of frames to acquire. If None, acquires indefinitely until stopped.
            trigger_mode: The trigger mode to use. Defaults to TriggerMode.ON.
            trigger_polarity: The trigger polarity to use. Defaults to None.
        """
        if not self._buffer_allocated:
            self.allocate_buffer()
        self.trigger_mode = trigger_mode
        self.trigger_polarity = trigger_polarity
        self._configure_trigger_mode(self.trigger_mode)
        self._configure_trigger_polarity(self.trigger_polarity)
        self._start(frame_count)

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer.

        If binning is via software, the GPU binned
        image is computed and returned.

        Returns:
            The camera frame of size (height, width).

        Raises:
            RuntimeError: If the camera is not started.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop the camera."""

"""Camera device handle with typed methods."""

from typing import TYPE_CHECKING, cast

from ome_zarr_writer import WriterSettings
from rigup.device.handle import Adapter, DeviceProperty
from vxlib.vec import IVec2D, Vec2D

from rigup import DeviceHandle
from vxl.camera.base import (
    Camera,
    CaptureState,
    DatasetRef,
    SensorROI,
    Storage,
    StorageStatus,
    TriggerMode,
    TriggerPolarity,
)
from vxl.camera.preview import PreviewConfig, PreviewLevels, PreviewViewport
from vxlib import Coalescer

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class CameraHandle(DeviceHandle[Camera]):
    """Camera handle with typed methods for preview operations.

    Works with both local and remote cameras - the transport handles
    the communication details.

    Live preview tuning is exposed as coalescers — ``camera.preview_viewport.update(v)``
    collapses rapid updates to the latest (one RPC in flight) and ``.cancel()`` (e.g. on
    stop_preview) discards anything pending. Each drains to a private ``_set_preview_*``.
    """

    def __init__(self, adapter: Adapter[Camera]) -> None:
        super().__init__(adapter)
        self.preview_viewport: Coalescer[PreviewViewport] = Coalescer(drain=self._set_preview_viewport)
        self.preview_levels: Coalescer[PreviewLevels] = Coalescer(drain=self._set_preview_levels)
        self.preview_colormap: Coalescer[str | None] = Coalescer(drain=self._set_preview_colormap)
        self.roi: DeviceProperty[SensorROI] = self.props.property("roi", SensorROI.model_validate)
        self.frame_area_um: DeviceProperty[Vec2D] = self.props.property("frame_area_um", self._parse_vec2d)
        self.pixel_size_um: DeviceProperty[Vec2D] = self.props.property("pixel_size_um", self._parse_vec2d)
        self.sensor_size_px: DeviceProperty[IVec2D] = self.props.property("sensor_size_px", self._parse_ivec2d)
        self.preview_config: DeviceProperty[PreviewConfig] = self.props.property(
            "preview_config", PreviewConfig.model_validate
        )
        self.ready_for_batch: DeviceProperty[bool] = self.props.property("ready_for_batch", bool)

    async def start_preview(
        self,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start camera preview mode.

        Args:
            trigger_mode: Trigger mode (default: TriggerMode.ON)
            trigger_polarity: Trigger polarity (default: TriggerPolarity.RISING_EDGE)

        Returns:
            Topic name where preview frames will be published.
        """
        result = await self.call("start_preview", trigger_mode, trigger_polarity)
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            raise RuntimeError(f"{self.uid} failed to start preview: {result.get('msg', result)}")
        raise RuntimeError(f"{self.uid} failed to start preview: returned unexpected type {type(result)}: {result}")

    async def stop_preview(self) -> None:
        """Stop camera preview mode."""
        await self.call("stop_preview")

    async def clear_preview_cache(self) -> None:
        """Clear cached frame on camera. Called on profile change."""
        await self.call("clear_preview_cache")

    async def _set_preview_viewport(self, viewport: PreviewViewport) -> None:
        """Apply a preview viewport to the camera — drain for ``preview_viewport``."""
        await self.call("update_preview_viewport", viewport)

    async def _set_preview_levels(self, levels: PreviewLevels) -> None:
        """Apply preview levels to the camera — drain for ``preview_levels``."""
        await self.call("update_preview_levels", levels)

    async def _set_preview_colormap(self, colormap: str | None) -> None:
        """Apply a preview colormap to the camera — drain for ``preview_colormap``."""
        await self.call("update_preview_colormap", colormap)

    # Legacy direct setters — used only by the old controllers/preview.py; remove with it.
    async def update_preview_viewport(self, viewport: PreviewViewport) -> None:
        """Apply a preview viewport now (uncoalesced). Prefer ``preview_viewport.update``."""
        await self._set_preview_viewport(viewport)

    async def update_preview_levels(self, levels: PreviewLevels) -> None:
        """Apply preview levels now (uncoalesced). Prefer ``preview_levels.update``."""
        await self._set_preview_levels(levels)

    async def update_preview_colormap(self, colormap: str | None) -> None:
        """Apply a preview colormap now (uncoalesced). Prefer ``preview_colormap.update``."""
        await self._set_preview_colormap(colormap)

    async def auto_level(self, percentile: float = 1.0) -> None:
        """Auto-set preview levels from the camera's latest overview histogram (percentile clip)."""
        await self.call("auto_level", percentile)

    async def get_preview_config(self) -> PreviewConfig:
        """Get the current preview display configuration."""
        result = await self.call("get_preview_config")
        return PreviewConfig.model_validate(result)

    async def check_writable(self, storage: Storage) -> StorageStatus:
        """Preflight: prove this camera's node can write ``storage``. Raises if not. Returns the
        node's storage status (host, resolved root, free bytes)."""
        result = await self.call("check_writable", storage=storage)
        return StorageStatus.model_validate(result)

    async def open_stack(
        self,
        *,
        storage: Storage,
        num_frames: int,
        z_step: float,
        magnification: float,
        settings: WriterSettings,
    ) -> DatasetRef:
        """Prepare camera and writer for a stack acquisition; return a pointer to its dataset.

        ``storage`` is the per-channel logical destination (the node resolves it);
        ``settings`` are the broadcast output-format knobs. ``magnification`` converts
        the sensor-space pixel size into the sample-space lateral voxel size. The returned
        :class:`DatasetRef` is persisted by control as ``<channel>.ref.json``.
        """
        result = await self.call(
            "open_stack",
            storage=storage,
            num_frames=num_frames,
            z_step=z_step,
            magnification=magnification,
            settings=settings,
        )
        return DatasetRef.model_validate(result)

    async def close_stack(self) -> None:
        """Start draining and closing the writer in the background. Poll capture_state until CLOSED."""
        await self.call("close_stack")

    async def begin_batch(self, num_frames: int) -> None:
        """Arm and start grabbing num_frames frames in the background. Poll capture_state for completion."""
        await self.call("begin_batch", num_frames)

    async def capture_state(self) -> CaptureState:
        """Lifecycle of the most recent begin_batch/close_stack. Raises if the task failed."""
        result = await self.call("capture_state")
        return CaptureState(result)

    async def update_roi(self, roi: SensorROI) -> SensorROI:
        """Set sensor ROI. Returns the actual applied ROI (may differ due to alignment)."""
        result = await self.call("update_roi", roi)
        return SensorROI.model_validate(result)

    async def reset_roi(self) -> SensorROI:
        """Reset the sensor ROI to the full sensor. Returns the applied ROI."""
        result = await self.call("reset_roi")
        return SensorROI.model_validate(result)

    @staticmethod
    def _parse_vec2d(value: object) -> Vec2D:
        """Parse a Vec2D property, handling its "y,x" string serialization over ZMQ."""
        if isinstance(value, Vec2D):
            return value
        if isinstance(value, str):
            return Vec2D.from_str(value)
        if isinstance(value, (list, tuple)):
            seq = cast("Sequence[int | float]", value)
            return Vec2D(y=seq[0], x=seq[1])
        mapping = cast("Mapping[str, int | float]", value)
        return Vec2D(y=mapping["y"], x=mapping["x"])

    @staticmethod
    def _parse_ivec2d(value: object) -> IVec2D:
        """Parse an IVec2D property, handling its "y,x" string serialization over ZMQ."""
        if isinstance(value, IVec2D):
            return value
        if isinstance(value, str):
            return IVec2D.from_str(value)
        if isinstance(value, (list, tuple)):
            seq = cast("Sequence[int]", value)
            return IVec2D(y=seq[0], x=seq[1])
        mapping = cast("Mapping[str, int]", value)
        return IVec2D(y=mapping["y"], x=mapping["x"])

    # async def get_frame_area_um(self) -> Vec2D:
    #     """Get the physical frame area in micrometers."""
    #     return await self.frame_area_um.get()

    # async def get_pixel_size_um(self) -> Vec2D:
    #     """Get the sensor pixel size in micrometers."""
    #     return await self.pixel_size_um.get()

    # async def get_sensor_size_px(self) -> IVec2D:
    #     """Get the full sensor size in pixels."""
    #     return await self.sensor_size_px.get()

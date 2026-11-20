"""Camera device handle with typed methods."""

from pathlib import PurePosixPath

from ome_zarr_writer import WriterSettings
from pydantic import TypeAdapter
from rigup.device import DeviceHandle
from rigup.device.handle import Adapter, PropView
from vxlib.coalescer import Coalescer
from vxlib.vector import Vec2D

from vxl.devices.camera.area import AreaCamera, AreaROI
from vxl.devices.camera.base import Camera, CameraSensor, CaptureState, TriggerMode, TriggerPolarity
from vxl.live import LiveViewport
from vxl.storage import ImageLocation, StorageSpec, StorageStatus

_IMAGE_LOCATION_ADAPTER = TypeAdapter(ImageLocation)
_REMOTE_STORES_ADAPTER = TypeAdapter(dict[str, str])


class CameraHandle[D: Camera](DeviceHandle[D]):
    """Any camera's handle: its node's storage."""

    async def check_writable(self, storage: StorageSpec) -> StorageStatus:
        """Preflight: prove this camera's node can write ``storage``. Raises if not. Returns the
        node's storage status (host, resolved root, free bytes)."""
        result = await self.call("check_writable", storage=storage)
        return StorageStatus.model_validate(result)

    async def remote_stores(self) -> dict[str, str]:
        """Return this camera host's configured object stores as name-to-fingerprint mappings."""
        return _REMOTE_STORES_ADAPTER.validate_python(await self.call("remote_stores"))


class AreaCameraHandle(CameraHandle[AreaCamera]):
    """Area camera handle with typed methods for preview operations.

    Works with both local and remote cameras - the transport handles
    the communication details.

    Viewport updates are coalesced: ``camera.live_viewport.update(v)`` collapses rapid
    updates to the latest with one RPC in flight.
    """

    def __init__(self, adapter: Adapter[AreaCamera]) -> None:
        super().__init__(adapter)
        self.live_viewport: Coalescer[LiveViewport] = Coalescer(drain=self._set_live_viewport)
        self.roi: PropView[AreaROI] = self.props.view("roi", AreaROI.model_validate)
        self.frame_area_um: PropView[Vec2D] = self.props.view("frame_area_um", Vec2D.parse)
        self.sensor: PropView[CameraSensor] = self.props.view("sensor", CameraSensor.model_validate)
        self.ready_for_batch: PropView[bool] = self.props.view("ready_for_batch", bool)

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

    async def close_live_updates(self) -> None:
        """Stop and await the handle-owned preview update workers."""
        await self.live_viewport.close()

    async def reset_live_stream(self) -> str:
        """End the current preview source stream and return its replacement identity."""
        result = await self.call("reset_live_stream")
        if not isinstance(result, str):
            raise RuntimeError(f"{self.uid} returned an invalid preview source-stream identity")
        return result

    async def _set_live_viewport(self, viewport: LiveViewport) -> None:
        """Apply a preview viewport to the camera — drain for ``live_viewport``."""
        await self.call("update_live_viewport", viewport)

    async def open_stack(
        self,
        *,
        storage: StorageSpec,
        subpath: PurePosixPath,
        num_frames: int,
        z_step: float,
        magnification: float,
        settings: WriterSettings,
    ) -> ImageLocation:
        """Prepare camera and writer for a stack acquisition; return its durable dataset location.

        ``storage`` is the run's logical destination and ``subpath`` the dataset's relative location
        under it (the node resolves it against machine-local storage); ``settings`` are the broadcast
        output-format knobs. ``magnification`` converts the sensor-space pixel size into the
        sample-space lateral voxel size. OME-Zarr metadata remains authoritative for dataset geometry.
        """
        result = await self.call(
            "open_stack",
            storage=storage,
            subpath=subpath,
            num_frames=num_frames,
            z_step=z_step,
            magnification=magnification,
            settings=settings,
        )
        return _IMAGE_LOCATION_ADAPTER.validate_python(result)

    async def close_stack(self) -> None:
        """Start draining and closing the writer in the background. Poll capture_state until CLOSED."""
        await self.call("close_stack")

    async def release_writer(self) -> None:
        """Free the writer ring (workers + shared memory); the next open_stack re-allocates it cold."""
        await self.call("release_writer")

    async def begin_batch(self, num_frames: int) -> None:
        """Arm and start grabbing num_frames frames in the background. Poll capture_state for completion."""
        await self.call("begin_batch", num_frames)

    async def capture_state(self) -> CaptureState:
        """Lifecycle of the most recent begin_batch/close_stack. Raises if the task failed."""
        result = await self.call("capture_state")
        return CaptureState(result)

    async def update_roi(self, roi: AreaROI) -> AreaROI:
        """Set sensor ROI. Returns the actual applied ROI (may differ due to alignment)."""
        result = await self.call("update_roi", roi)
        return AreaROI.model_validate(result)

    async def reset_roi(self) -> AreaROI:
        """Reset the sensor ROI to the full sensor. Returns the applied ROI."""
        result = await self.call("reset_roi")
        return AreaROI.model_validate(result)

    # async def get_frame_area_um(self) -> Vec2D:
    #     """Get the physical frame area in micrometers."""
    #     return await self.frame_area_um.get()

    # async def get_pixel_size_um(self) -> Vec2D:
    #     """Get the sensor pixel size in micrometers."""
    #     return await self.pixel_size_um.get()

    # async def get_sensor_size_px(self) -> IVec2D:
    #     """Get the full sensor size in pixels."""
    #     return await self.sensor_size_px.get()

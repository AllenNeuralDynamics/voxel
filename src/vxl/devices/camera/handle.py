"""Camera device handle with typed methods."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from pathlib import PurePosixPath

from ome_zarr_writer import WriterSettings
from pydantic import TypeAdapter
from rigup.device import DeviceHandle
from rigup.device.handle import Adapter, PropView
from vxlib.coalescer import Coalescer
from vxlib.imaging.writer import FrameRange, WhenFull, WriterProgress
from vxlib.vector import Transform, Vec2D

from vxl.devices.camera.area import AreaCamera, AreaROI
from vxl.devices.camera.base import Camera, CameraSensor, CaptureState, CaptureStatus, TriggerMode, TriggerPolarity
from vxl.live import LiveViewport
from vxl.storage import ImageLocation, StorageSpec, StorageStatus

_IMAGE_LOCATION_ADAPTER = TypeAdapter(ImageLocation)
_REMOTE_STORES_ADAPTER = TypeAdapter(dict[str, str])
_FRAME_RANGES_ADAPTER = TypeAdapter(list[FrameRange])

_RECHECK_S = 5.0
"""How often a wait for the camera reads its status again: a camera that no longer answers ends the wait."""


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
        self.progress: PropView[WriterProgress] = self.props.view("progress", WriterProgress.model_validate)
        self.capture: PropView[CaptureStatus] = self.props.view("capture", CaptureStatus.model_validate)

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
            raise RuntimeError(f"{self.id} failed to start preview: {result.get('msg', result)}")
        raise RuntimeError(f"{self.id} failed to start preview: returned unexpected type {type(result)}: {result}")

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
            raise RuntimeError(f"{self.id} returned an invalid preview source-stream identity")
        return result

    async def _set_live_viewport(self, viewport: LiveViewport) -> None:
        """Apply a preview viewport to the camera — drain for ``live_viewport``."""
        await self.call("update_live_viewport", viewport)

    async def open_image(
        self,
        *,
        storage: StorageSpec,
        subpath: PurePosixPath,
        transform: Transform,
        settings: WriterSettings,
        when_full: WhenFull = "wait",
    ) -> ImageLocation:
        """Prepare the camera and its writer for 1 image, and give the image's location while it is written.
        ``transform`` gives the frame count and where each pixel sits; ``settings`` are the writer's own;
        ``when_full`` is what a batch does when every buffer is busy."""
        result = await self.call(
            "open_image", storage=storage, subpath=subpath, transform=transform, settings=settings, when_full=when_full
        )
        return _IMAGE_LOCATION_ADAPTER.validate_python(result)

    async def close_image(self) -> None:
        """Write what is left of the open image, close it, and wait until it is closed. A cancel lets the close end
        first, so a stop never leaves an image half closed with nobody waiting for it. Raise when the close failed or
        the camera stopped answering."""
        closing = asyncio.ensure_future(self._close_image())
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            with suppress(Exception):
                await closing
            raise

    async def _close_image(self) -> None:
        number = await self.call("close_image")
        await self._wait_for(lambda s: s.batch == number and (s.state is CaptureState.CLOSED or s.error is not None))

    async def wait_for_batch(self, batch: int) -> None:
        """Wait until batch ``batch`` of :meth:`begin_batch` is done. Raise when it failed."""
        await self._wait_for(lambda s: s.batch == batch and (s.state is CaptureState.DONE or s.error is not None))

    async def wait_until_collected(self) -> None:
        """Wait until the camera collects no more frames: its batch is done, or has failed."""
        await self._wait_for(lambda status: status.state is not CaptureState.COLLECTING, raise_on_error=False)

    async def _wait_for(self, reached: Callable[[CaptureStatus], bool], *, raise_on_error: bool = True) -> None:
        """Wait until :attr:`capture` is ``reached``, followed as the camera streams it and read again every
        ``_RECHECK_S``. The read again ends the wait when the camera's process is gone, and catches a change the
        stream did not bring. Raise when the status reached carries an error, unless not ``raise_on_error``."""
        found = asyncio.get_running_loop().create_future()

        def check(status: CaptureStatus) -> None:
            if not found.done() and reached(status):
                found.set_result(status)

        teardown = self.capture.subscribe(check)
        try:
            while not found.done():
                try:
                    check(await self.capture.get())
                except (ConnectionError, TimeoutError) as error:
                    raise RuntimeError(f"{self.id} stopped answering: {error!r}") from error
                await asyncio.wait({found}, timeout=_RECHECK_S)
            status: CaptureStatus = found.result()
        finally:
            teardown()
        if raise_on_error and status.error is not None:
            raise RuntimeError(f"{self.id} capture failed: {status.error}")

    async def batch_frames(self) -> int:
        """The frames in 1 batch of the open image's writer: a step scan arms the camera for at most this many."""
        return await self.call("batch_frames")

    async def dropped(self) -> list[FrameRange]:
        """The frames of the open image that the writer dropped because every buffer was busy."""
        return _FRAME_RANGES_ADAPTER.validate_python(await self.call("dropped"))

    async def release_writer(self) -> None:
        """Free the writer's buffers (its workers and shared memory); the next image allocates them again."""
        await self.call("release_writer")

    async def begin_batch(self, num_frames: int) -> int:
        """Arm and start grabbing ``num_frames`` frames in the background, and give back the batch's number in
        :attr:`capture`, to pass to :meth:`wait_for_batch`."""
        return await self.call("begin_batch", num_frames)

    async def capture_state(self) -> CaptureState:
        """Where the most recent :meth:`begin_batch` or :meth:`close_image` is. Raises if it failed."""
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

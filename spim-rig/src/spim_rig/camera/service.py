import asyncio
import logging
from enum import StrEnum

import zmq.asyncio

# from ome_zarr_writer import Backend as WriterBackend
from pyrig import DeviceAddress, DeviceAddressTCP, DeviceService, describe
from spim_rig.camera.base import SpimCamera, TriggerMode, TriggerPolarity  # , TriggerMode, TriggerPolarity
from spim_rig.camera.preview import PreviewCrop, PreviewFrame, PreviewGenerator, PreviewIntensity


class CameraMode(StrEnum):
    IDLE = "IDLE"
    PREVIEW = "PREVIEW"
    ACQUISITION = "ACQUISITION"


class CameraService(DeviceService[SpimCamera]):
    def __init__(self, device: SpimCamera, conn: DeviceAddress, zctx: zmq.asyncio.Context):
        # Initialize state BEFORE super().__init__() which calls _collect_commands()
        self._channel_name = device.uid
        self._mode = CameraMode.IDLE
        self._preview_task: asyncio.Task | None = None
        self._frame_idx = 0

        # Frame publishing socket
        self._preview_socket = zctx.socket(zmq.PUB)
        self._preview_socket.setsockopt(zmq.SNDHWM, 10)

        self._previewer = PreviewGenerator(sink=self._publish_preview, uid=device.uid)

        # Call super after initializing state
        super().__init__(device, conn, zctx)

    @property
    @describe(label="Camera Mode", desc="Current operating mode")
    def mode(self) -> CameraMode:
        """Current camera operating mode."""
        return self._mode

    def _publish_preview(self, frame: PreviewFrame) -> None:
        """Publish preview frame to subscribers."""
        if self._preview_task is None or self._mode != CameraMode.PREVIEW:
            return

        topic = f"preview/{self._channel_name}".encode()
        try:
            self._preview_socket.send_multipart([topic, frame.pack()], flags=zmq.NOBLOCK)
        except zmq.Again:
            self.log.warning("Preview buffer full, dropping frame")

    @describe(label="Update Preview Crop")
    async def update_preview_crop(self, crop: PreviewCrop):
        """Update preview crop settings."""
        self._previewer.crop = crop

    @describe(label="Update Preview Intensity")
    async def update_preview_intensity(self, intensity: PreviewIntensity):
        """Update preview intensity range."""
        self._previewer.intensity = intensity

    @describe(label="Start Preview", desc="Start live preview mode")
    async def start_preview(
        self,
        channel_name: str,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> str:
        """Start preview mode - live view before acquisition.

        Camera runs continuously in free-running mode, frames published via PUB socket.

        Args:
            channel_name: Channel identifier for preview topic and metadata
            trigger_mode: Trigger mode for preview (default: ON)
            trigger_polarity: Trigger polarity for preview (default: RISING_EDGE)

        Returns:
            Preview address to connect to (e.g., "tcp://192.168.1.10:6000")
        """
        if self._mode != CameraMode.IDLE:
            raise RuntimeError(f"Cannot start preview: camera in {self._mode} mode")

        # Set channel name for this session
        self._channel_name = channel_name

        # Allocate port and bind preview socket
        preview_port = self._preview_socket.bind_to_random_port("tcp://*")

        # Return connectable address using client-facing connection (not the bound 0.0.0.0)

        if isinstance(self._client_conn, DeviceAddressTCP):
            host = self._client_conn.host
        else:
            host = "127.0.0.1"  # Fallback for IPC/INPROC

        preview_addr = f"tcp://{host}:{preview_port}"

        # Prepare camera for preview with trigger settings
        def _prepare_and_start():
            self.device.prepare(trigger_mode=trigger_mode, trigger_polarity=trigger_polarity)
            self.device.start(frame_count=None)

        await self._exec(_prepare_and_start)

        # Start preview loop
        self._mode = CameraMode.PREVIEW
        self._frame_idx = 0
        self._preview_task = asyncio.create_task(self._preview_loop())

        self.log.info(f"Preview mode started on channel '{channel_name}' at {preview_addr}")

        return preview_addr

    @describe(label="Stop Preview", desc="Stop preview mode")
    async def stop_preview(self):
        """Stop preview mode."""
        if self._mode != CameraMode.PREVIEW:
            self.log.warning(f"Not in preview mode (current: {self._mode})")
            return

        self._mode = CameraMode.IDLE

        if self._preview_task:
            await self._preview_task
            self._preview_task = None
        await self._exec(self.device.stop)

        self.log.info("Preview mode stopped")

    async def _preview_loop(self):
        """Preview loop - continuously grab and publish frames."""
        try:
            while self._mode == CameraMode.PREVIEW:
                # Grab frame from camera
                frame = await self._exec(self.device.grab_frame)

                # Process frame asynchronously (offloaded to preview generator's executor)
                await self._previewer.new_frame(frame, idx=self._frame_idx)

                self._frame_idx += 1

                # Log actual frame rate periodically using stream_info (every 10 frames)
                if self._frame_idx > 0 and self._frame_idx % 10 == 0:
                    stream_info = self.device.stream_info
                    if stream_info:
                        self.log.info(
                            f"Preview: {self._frame_idx} frames, "
                            f"{stream_info.frame_rate_fps:.1f} fps, "
                            f"{stream_info.data_rate_mbs:.1f} MB/s"
                        )

        except asyncio.CancelledError:
            self.log.info("Preview loop cancelled")
        except Exception as e:
            self.log.error(f"Preview loop error: {e}", exc_info=True)
            self._mode = CameraMode.IDLE

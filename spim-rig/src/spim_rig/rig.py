import asyncio

import zmq.asyncio

from pyrig import DeviceClient, DeviceType, Rig, RigConfig
from pyrig.node import DeviceProvision
from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.client import CameraClient
from spim_rig.node import SpimNodeService
from spim_rig.preview_hub import RigPreviewHub


class SpimRig(Rig):
    """SPIM microscope rig orchestration."""

    NODE_SERVICE_CLASS = SpimNodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: RigConfig):
        super().__init__(zctx=zctx, config=config)
        self.cameras: dict[str, CameraClient] = {}

        # Preview management (independent of rig internals)
        self.preview = RigPreviewHub(zctx, name=f"{self.__class__.__name__}.PreviewManager")

    def _create_client(self, device_id: str, prov: DeviceProvision) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        match prov.device_type:
            case DeviceType.CAMERA:
                client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.cameras[device_id] = client
                return client
            case _:
                return super()._create_client(device_id, prov)

    async def start_preview(
        self,
        trigger_mode: TriggerMode = TriggerMode.ON,
        trigger_polarity: TriggerPolarity = TriggerPolarity.RISING_EDGE,
    ) -> None:
        """Start preview mode on all cameras and begin frame streaming.

        Orchestrates camera preview startup and connects preview manager to camera streams.

        Args:
            trigger_mode: Trigger mode for all cameras (default: TriggerMode.ON)
            trigger_polarity: Trigger polarity for all cameras (default: TriggerPolarity.RISING_EDGE)
        """
        if self.preview.is_active:
            self.log.warning("Preview already running")
            return

        self.log.info(f"Starting preview on {len(self.cameras)} cameras...")

        # Start all cameras in parallel, collect preview addresses
        results = await asyncio.gather(
            *[
                camera.start_preview(
                    channel_name=camera_id,
                    trigger_mode=trigger_mode,
                    trigger_polarity=trigger_polarity,
                )
                for camera_id, camera in self.cameras.items()
            ],
            return_exceptions=True,
        )

        # Collect successful preview addresses
        preview_addrs: dict[str, str] = {}
        for camera_id, result in zip(self.cameras.keys(), results):
            if isinstance(result, BaseException):
                self.log.error(f"Camera {camera_id} failed to start preview: {result}")
            else:
                preview_addrs[camera_id] = result  # Address returned by camera (e.g., "tcp://127.0.0.1:63495")

        # Start preview manager with collected addresses
        await self.preview.start(preview_addrs)

    async def stop_preview(self) -> None:
        """Stop preview mode on all cameras and cleanup manager."""
        if not self.preview.is_active:
            self.log.warning("Preview not running")
            return

        self.log.info("Stopping preview...")

        # Stop preview manager first
        await self.preview.stop()

        # Then stop all cameras
        tasks = [camera.stop_preview() for camera in self.cameras.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.log.info("Preview stopped")

import asyncio
from collections.abc import Coroutine

import zmq.asyncio

from pyrig import DeviceClient, DeviceType, Rig, RigConfig
from pyrig.node import DeviceProvision
from spim_rig.camera.client import CameraClient
from spim_rig.camera.preview import PreviewFrame
from spim_rig.node import SpimNodeService


class SpimRig(Rig):
    """SPIM microscope rig orchestration."""

    NODE_SERVICE_CLASS = SpimNodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: RigConfig):
        super().__init__(zctx=zctx, config=config)
        self.cameras: dict[str, CameraClient] = {}

        # Single SUB socket for all camera frames
        self._preview_sub = zctx.socket(zmq.SUB)
        self._preview_sub.setsockopt(zmq.RCVHWM, 10)
        self._preview_sub.subscribe(b"preview/")

    def _create_client(self, device_id: str, prov: DeviceProvision) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        match prov.device_type:
            case DeviceType.CAMERA:
                client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.cameras[device_id] = client
                return client
            case _:
                return super()._create_client(device_id, prov)

    async def start_preview(self):
        """Start preview mode on all cameras.

        Cameras bind their own preview ports and return addresses.
        Rig connects to each camera's preview address.
        Channel names default to camera UIDs.
        """
        self.log.info(f"Starting preview on {len(self.cameras)} cameras...")

        # Start all cameras in parallel, collect addresses
        results = await asyncio.gather(
            *[camera.start_preview(channel_name=camera_id) for camera_id, camera in self.cameras.items()],
            return_exceptions=True,
        )

        for camera_id, result in zip(self.cameras.keys(), results):
            if isinstance(result, BaseException):
                self.log.error(f"Camera {camera_id} failed to start preview: {result}")
            else:
                preview_addr = result  # Address returned by camera (e.g., "tcp://127.0.0.1:63495")
                self._preview_sub.connect(preview_addr)
                self.log.info(f"Camera {camera_id} preview at {preview_addr}")

    async def receive_frames(self):
        """Async generator yielding (channel, frame) tuples."""
        while True:
            topic, payload = await self._preview_sub.recv_multipart()
            channel = topic.decode().split("/")[1]
            frame = PreviewFrame.from_packed(payload)
            yield channel, frame

    async def stop_preview(self):
        """Stop preview mode on all cameras."""
        self.log.info("Stopping preview on all cameras...")

        tasks: list[Coroutine] = [camera.stop_preview() for camera in self.cameras.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        self.log.info("Preview stopped on all cameras")

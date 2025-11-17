import asyncio

import zmq.asyncio

from pyrig import DeviceClient, Rig
from pyrig.node import DeviceProvision
from spim_rig.camera.base import TriggerMode, TriggerPolarity
from spim_rig.camera.client import CameraClient
from spim_rig.config import DeviceType, SpimRigConfig
from spim_rig.daq.client import DaqClient
from spim_rig.node import SpimNodeService
from spim_rig.preview_hub import RigPreviewHub


class SpimRig(Rig):
    """SPIM microscope rig orchestration."""

    NODE_SERVICE_CLASS = SpimNodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: SpimRigConfig):
        super().__init__(zctx=zctx, config=config)
        self.config: SpimRigConfig = config
        self.cameras: dict[str, CameraClient] = {}
        self.lasers: dict[str, DeviceClient] = {}
        self.fws: dict[str, DeviceClient] = {}
        self.daq: DaqClient | None = None

        # Preview management (independent of rig internals)
        self.preview = RigPreviewHub(zctx, name=f"{self.__class__.__name__}.PreviewManager")

    def _create_client(self, device_id: str, prov: DeviceProvision) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        match prov.device_type:
            case DeviceType.CAMERA:
                client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.cameras[device_id] = client
                return client
            case DeviceType.LASER:
                client = super()._create_client(device_id, prov)
                self.lasers[device_id] = client
                return client
            case DeviceType.FILTER_WHEEL:
                client = super()._create_client(device_id, prov)
                self.fws[device_id] = client
                return client
            case DeviceType.DAQ:
                client = DaqClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.daq = client
                return client
            case _:
                return super()._create_client(device_id, prov)

    async def _on_provision_complete(self) -> None:
        """Validate SPIM-specific device type assignments."""
        self._validate_device_types()

    def _validate_device_types(self) -> None:
        """Validate device type assignments after provisioning."""
        errors = []

        # Validate single DAQ
        if self.daq is None:
            errors.append(f"DAQ device '{self.config.daq.device}' was not provisioned")

        # Validate 1:1 camera <-> detection path mapping
        camera_ids = set(self.cameras.keys())
        detection_ids = set(self.config.detection.keys())

        missing_detection = camera_ids - detection_ids
        if missing_detection:
            errors.append(f"Cameras without detection paths: {missing_detection}")

        invalid_detection = detection_ids - camera_ids
        if invalid_detection:
            errors.append(f"Detection paths referencing non-camera devices: {invalid_detection}")

        # Validate 1:1 laser <-> illumination path mapping
        laser_ids = set(self.lasers.keys())
        illumination_ids = set(self.config.illumination.keys())

        missing_illumination = laser_ids - illumination_ids
        if missing_illumination:
            errors.append(f"Lasers without illumination paths: {missing_illumination}")

        invalid_illumination = illumination_ids - laser_ids
        if invalid_illumination:
            errors.append(f"Illumination paths referencing non-laser devices: {invalid_illumination}")

        # Validate DAQ device matches config
        if self.daq is not None and self.daq.uid != self.config.daq.device:
            errors.append(f"DAQ device mismatch: expected '{self.config.daq.device}', got '{self.daq.uid}'")

        # Validate aux_devices are not cameras, lasers, or DAQ
        reserved_devices = camera_ids | laser_ids | ({self.daq.uid} if self.daq else set())

        for path_id, path in self.config.detection.items():
            for aux in path.aux_devices:
                if aux in reserved_devices:
                    errors.append(f"Aux device '{aux}' in detection path '{path_id}' is a reserved device type")

        for path_id, path in self.config.illumination.items():
            for aux in path.aux_devices:
                if aux in reserved_devices:
                    errors.append(f"Aux device '{aux}' in illumination path '{path_id}' is a reserved device type")

        if errors:
            raise ValueError("SPIM device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    async def start_preview(self, trigger_mode: TriggerMode, trigger_polarity: TriggerPolarity) -> None:
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

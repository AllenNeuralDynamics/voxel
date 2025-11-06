import zmq.asyncio

from imaging.drivers.camera import CameraClient
from imaging.drivers.laser import LaserClient
from imaging.node import ImagingNodeService
from pyrig import Rig, RigConfig, DeviceClient, DeviceType
from pyrig.node import ProvisionedDevice


class ImagingRig(Rig):
    NODE_SERVICE_CLASS = ImagingNodeService

    def __init__(self, zctx: zmq.asyncio.Context, config: RigConfig):
        super().__init__(zctx, config)
        self.lasers: dict[str, LaserClient] = {}
        self.cameras: dict[str, CameraClient] = {}

    def _create_client(self, device_id: str, prov: ProvisionedDevice) -> DeviceClient:
        """Create a single client. Override for custom client types."""
        match prov.device_type:
            case DeviceType.LASER:
                client = LaserClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.lasers[device_id] = client
                return client
            case DeviceType.CAMERA:
                client = CameraClient(uid=device_id, zctx=self.zctx, conn=prov.conn)
                self.cameras[device_id] = client
                return client
            case _:
                return super()._create_client(device_id, prov)

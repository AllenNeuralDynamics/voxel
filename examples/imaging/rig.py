import zmq.asyncio

from imaging.drivers.camera import CameraHandle
from imaging.drivers.laser import LaserHandle
from imaging.node import ImagingNodeService
from pyrig import DeviceHandle, Rig, RigConfig
from pyrig.cluster import ClusterManager, DeviceProvision, ZMQAdapter


class ImagingClusterManager(ClusterManager):
    """Cluster manager that creates typed handles for imaging devices."""

    NODE_SERVICE_CLASS = ImagingNodeService

    def _create_handle(self, device_id: str, prov: DeviceProvision) -> DeviceHandle:
        """Create typed handles for laser and camera devices."""
        adapter = ZMQAdapter(
            uid=device_id,
            zctx=self.zctx,
            conn=prov.conn,
        )
        match prov.device_type:
            case "laser":
                return LaserHandle(adapter)
            case "camera":
                return CameraHandle(adapter)
            case _:
                return DeviceHandle(adapter)


class ImagingRig(Rig):
    CLUSTER_CLASS = ImagingClusterManager

    def __init__(self, config: RigConfig, zctx: zmq.asyncio.Context | None = None):
        super().__init__(config, zctx)
        self.lasers: dict[str, LaserHandle] = {}
        self.cameras: dict[str, CameraHandle] = {}

    async def _on_start_complete(self) -> None:
        """Categorize handles by device type after startup."""
        for device_id, handle in self.handles.items():
            if isinstance(handle, LaserHandle):
                self.lasers[device_id] = handle
            elif isinstance(handle, CameraHandle):
                self.cameras[device_id] = handle

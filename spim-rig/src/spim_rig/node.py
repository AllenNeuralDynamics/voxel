"""SPIM node service with custom device support.

The SpimNodeService extends pyrig's NodeService to support SPIM-specific devices
like SpimCamera, SpimDaq, and SpimAotf.

Note:
    To run a node, use the spim CLI:
        spim node <node_id> --rig <host[:port]>
    Or use the alias:
        spim-node <node_id> --rig <host[:port]>
"""

from pyrig import Device, DeviceHandle, NodeService
from pyrig.device import Adapter, DeviceAgent
from spim_rig.axes.linear.base import LinearAxis, LinearAxisAgent
from spim_rig.camera.base import CameraAgent, SpimCamera
from spim_rig.camera.handle import CameraHandle
from spim_rig.daq import DaqAgent, DaqHandle, SpimDaq
from spim_rig.device import DeviceType


class SpimNodeService(NodeService):
    """Node service with SPIM-specific device support.

    SpimCamera devices use CameraAgent for preview streaming.
    LinearAxis devices use LinearAxisAgent for TTL stepping support.
    SpimDaq devices use DaqAgent for task management.
    """

    @classmethod
    def create_agent(cls, device: Device) -> DeviceAgent:
        """Create custom agents for SPIM device types."""
        if isinstance(device, SpimCamera):
            return CameraAgent(device)
        if isinstance(device, LinearAxis):
            return LinearAxisAgent(device, stream_interval=0.05)
        if isinstance(device, SpimDaq):
            return DaqAgent(device)
        return super().create_agent(device)

    @classmethod
    def create_handle(cls, device_type: str, adapter: Adapter) -> DeviceHandle:
        """Create typed handles for SPIM device types."""
        match device_type:
            case DeviceType.CAMERA:
                return CameraHandle(adapter)
            case DeviceType.DAQ:
                return DaqHandle(adapter)
            case _:
                return super().create_handle(device_type, adapter)

"""SPIM node service with custom device support.

The SpimNodeService extends pyrig's NodeService to support SPIM-specific devices
like SpimCamera, SpimDaq, and SpimAotf.

Note:
    To run a node, use the spim CLI:
        spim node <node_id> --rig <host[:port]>
    Or use the alias:
        spim-node <node_id> --rig <host[:port]>
"""

from pyrig import Device, NodeService
from spim_rig.axes import SpimAxis
from spim_rig.camera.base import SpimCamera
from spim_rig.camera.service import CameraService
from spim_rig.daq.base import SpimDaq
from spim_rig.daq.service import DaqService


class SpimNodeService(NodeService):
    """Node service with SpimCamera, SpimDaq, and SpimAotf support."""

    def _create_service(self, device: Device, conn, stream_interval: float | None = None):
        """Hook for custom service types."""
        if isinstance(device, SpimCamera):
            return CameraService(device, conn, self._zctx)
        if isinstance(device, SpimDaq):
            return DaqService(device, conn, self._zctx)
        if isinstance(device, SpimAxis):
            return super()._create_service(device, conn, stream_interval=0.05)
        return super()._create_service(device, conn)

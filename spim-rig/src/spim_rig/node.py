"""Entry point for running a SpimNodeService on a remote host.

Usage:
    uv run python -m spim_rig.node <node_id> [controller_addr]

Examples:
    # Connect to controller on localhost
    uv run python -m spim_rig.node node_1

    # Connect to remote controller
    uv run python -m spim_rig.node node_1 tcp://192.168.1.100:9000
"""

from pyrig import Device, NodeService
from pyrig.node import main
from spim_rig.aotf.base import SpimAotf
from spim_rig.camera.base import SpimCamera
from spim_rig.camera.service import CameraService
from spim_rig.daq.base import SpimDaq
from spim_rig.daq.service import DaqService


class SpimNodeService(NodeService):
    """Node service with SpimCamera, SpimDaq, and SpimAotf support."""

    def _create_service(self, device: Device, conn):
        """Hook for custom service types."""
        if isinstance(device, SpimCamera):
            return CameraService(device, conn, self._zctx)
        if isinstance(device, SpimDaq):
            return DaqService(device, conn, self._zctx)
        if isinstance(device, SpimAotf):
            # AOTF uses the default DeviceService (no custom service needed)
            return super()._create_service(device, conn)
        return super()._create_service(device, conn)


if __name__ == "__main__":
    main(SpimNodeService)

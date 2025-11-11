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
from spim_rig.camera.base import SpimCamera
from spim_rig.camera.service import CameraService


class SpimNodeService(NodeService):
    """Node service with SpimCamera support."""

    def _create_service(self, device: Device, conn):
        """Hook for custom service types."""
        if isinstance(device, SpimCamera):
            return CameraService(device, conn, self._zctx)
        return super()._create_service(device, conn)


if __name__ == "__main__":
    main(SpimNodeService)

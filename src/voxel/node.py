"""Voxel node service with custom device support.

The VoxelRigNode extends pyrig's RigNode to support Voxel-specific devices
like Camera, VoxelDaq, and AOTF.

Usage:
    voxel-node <node_id> --rig <host[:port]>
"""

import argparse
import logging
import sys

from pyrig.cluster import run_node_service
from pyrig.device import Adapter, DeviceController
from pyrig.utils import configure_logging

from pyrig import Device, DeviceHandle, RigNode
from voxel.axes.continuous.base import ContinuousAxis, ContinuousAxisController
from voxel.axes.continuous.handle import ContinuousAxisHandle
from voxel.camera.base import Camera, CameraController
from voxel.camera.handle import CameraHandle
from voxel.daq import DaqController, DaqHandle, VoxelDaq
from voxel.device import DeviceType


class VoxelNode(RigNode):
    """Node service with Voxel-specific device support.

    Camera devices use CameraController for preview streaming.
    ContinuousAxis devices use ContinuousAxisController for TTL stepping support.
    VoxelDaq devices use DaqController for task management.
    """

    @classmethod
    def create_controller(cls, device: Device) -> DeviceController:
        """Create custom controllers for Voxel device types."""
        if isinstance(device, Camera):
            return CameraController(device)
        if isinstance(device, ContinuousAxis):
            return ContinuousAxisController(device, stream_interval=0.05)
        if isinstance(device, VoxelDaq):
            return DaqController(device)
        return super().create_controller(device)

    @classmethod
    def create_handle(cls, device_type: str, adapter: Adapter) -> DeviceHandle:
        """Create typed handles for Voxel device types."""
        match device_type:
            case DeviceType.CAMERA:
                return CameraHandle(adapter)
            case DeviceType.DAQ:
                return DaqHandle(adapter)
            case DeviceType.CONTINUOUS_AXIS:
                return ContinuousAxisHandle(adapter)
            case _:
                return super().create_handle(device_type, adapter)


def _create_node_parser() -> argparse.ArgumentParser:
    """Create the argument parser for node CLI."""
    parser = argparse.ArgumentParser(
        prog="voxel-node",
        description="Voxel Node Service - Manage devices on a node",
    )
    parser.add_argument("node_id", type=str, help="Node identifier (e.g., camera_1)")
    parser.add_argument("--rig", type=str, required=True, help="Rig controller address (host or host:port)")
    parser.add_argument("--log-port", type=int, default=9001, help="Controller log port (default: 9001)")
    parser.add_argument("--start-port", type=int, default=10000, help="Starting port for device services")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def node_main() -> None:
    """Entry point for voxel-node CLI."""
    args = _create_node_parser().parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("voxel.node")

    # Parse host:port
    if ":" in args.rig:
        ctrl_host, port_str = args.rig.split(":", 1)
        try:
            ctrl_port = int(port_str)
        except ValueError:
            log.error("Invalid port in --rig argument: %s", port_str)
            sys.exit(1)
    else:
        ctrl_host = args.rig
        ctrl_port = 9000

    log.info("Starting Voxel Node: %s", args.node_id)
    log.info("Rig controller: %s:%d", ctrl_host, ctrl_port)

    run_node_service(
        node_id=args.node_id,
        ctrl_host=ctrl_host,
        ctrl_port=ctrl_port,
        log_port=args.log_port,
        start_port=args.start_port,
        service_cls=VoxelNode,
    )

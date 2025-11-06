import logging

# Base classes for building rigs
from .rig import Rig
from .node import NodeService

# Device layer
from .device import Device, DeviceService, DeviceClient, DeviceType, describe

# Configuration
from .config import RigConfig, NodeConfig

# For custom services
from .device.conn import DeviceAddress, DeviceAddressTCP

# Set up library logging with NullHandler (users opt-in to see logs)
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    # Rig layer
    "Rig",
    "NodeService",
    # Device layer
    "Device",
    "DeviceService",
    "DeviceClient",
    "DeviceType",
    "describe",
    # Configuration
    "RigConfig",
    "NodeConfig",
    # Networking
    "DeviceAddress",
    "DeviceAddressTCP",
]

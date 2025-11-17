import logging

# Configuration
from .config import NodeConfig, RigConfig

# Device layer
from .device import Device, DeviceClient, DeviceService, describe

# For custom services
from .device.conn import DeviceAddress, DeviceAddressTCP
from .node import NodeService
from .props import PropertyModel

# Base classes for building rigs
from .rig import Rig

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
    "describe",
    "PropertyModel",
    # Configuration
    "RigConfig",
    "NodeConfig",
    # Networking
    "DeviceAddress",
    "DeviceAddressTCP",
]

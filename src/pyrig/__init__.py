import logging

# Configuration
from .config import NodeConfig, RigConfig

# Device layer
from .conn import DeviceAddress, DeviceAddressTCP, DeviceClient, DeviceService
from .device import Device, DeviceInterface, PropertyModel, describe

# For custom services
from .node import NodeService

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
    "DeviceInterface",
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

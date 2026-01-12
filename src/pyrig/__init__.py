import logging

from .cluster import (
    ClusterConfig,
    ClusterManager,
    DeviceAddress,
    DeviceAddressTCP,
    NodeConfig,
    RigNode,
    ZMQAdapter,
    ZMQService,
)
from .device import Adapter, Device, DeviceHandle, DeviceInterface, PropertyModel, describe
from .local import LocalAdapter
from .rig import Rig, RigConfig, RigInfo

# Set up library logging with NullHandler (users opt-in to see logs)
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    # Rig orchestration
    "Rig",
    "ClusterManager",
    # Device abstractions
    "Device",
    "DeviceHandle",
    "DeviceInterface",
    "Adapter",
    "LocalAdapter",
    # Network services
    "ZMQService",
    "ZMQAdapter",
    "RigNode",
    # Configuration
    "RigConfig",
    "RigInfo",
    "ClusterConfig",
    "NodeConfig",
    "DeviceAddress",
    "DeviceAddressTCP",
    # Utilities
    "describe",
    "PropertyModel",
]

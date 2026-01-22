import logging

from pyrig import (
    Adapter,
    ClusterConfig,
    ClusterManager,
    Device,
    DeviceAddress,
    DeviceAddressTCP,
    DeviceHandle,
    DeviceInterface,
    LocalAdapter,
    NodeConfig,
    PropertyModel,
    Rig,
    RigConfig,
    RigInfo,
    RigNode,
    ZMQAdapter,
    ZMQService,
    create_local_handle,
    describe,
)

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
    "create_local_handle",
]

"""Holds all device-related classes and interfaces serving as a Hardware Abstraction Layer (HAL).

For each supported device type, there is a corresponding interface class that defines the expected behavior and
properties.
Each device inherits from `VoxelDevice`
"""

from .base import VoxelDevice, VoxelDeviceConnectionError, VoxelDeviceError, VoxelDeviceType
from .interfaces.aotf import VoxelAOTF
from .interfaces.camera import VoxelCamera
from .interfaces.chiller import VoxelChiller
from .interfaces.filter_wheel import VoxelFilterWheel
from .interfaces.flip_mount import VoxelFlipMount
from .interfaces.laser import VoxelLaser
from .interfaces.linear_axis import LinearAxisDimension, VoxelLinearAxis
from .interfaces.power_meter import VoxelPowerMeter
from .interfaces.rotation_axis import VoxelRotationAxis
from .interfaces.tunable_lens import VoxelTunableLens

__all__ = [
    'LinearAxisDimension',
    'VoxelAOTF',
    'VoxelCamera',
    'VoxelChiller',
    'VoxelDevice',
    'VoxelDeviceConnectionError',
    'VoxelDeviceError',
    'VoxelDeviceType',
    'VoxelFilterWheel',
    'VoxelFlipMount',
    'VoxelLaser',
    'VoxelLinearAxis',
    'VoxelPowerMeter',
    'VoxelRotationAxis',
    'VoxelTunableLens',
]

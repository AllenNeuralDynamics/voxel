"""Holds all device-related classes and interfaces serving as a Hardware Abstraction Layer (HAL).

For each supported device type, there is a corresponding interface class that defines the expected behavior and
properties.
Each device inherits from `VoxelDevice`
"""

from .aotf.base import VoxelAOTF
from .camera.base import VoxelCamera
from .chiller.base import VoxelChiller
from .device import VoxelDevice, VoxelDeviceConnectionError, VoxelDeviceError, VoxelDeviceType
from .etl.base import VoxelTunableLens
from .filter_wheel.base import VoxelFilterWheel
from .flip_mount.base import VoxelFlipMount
from .laser.base import VoxelLaser
from .linear_axis.base import LinearAxisDimension, VoxelLinearAxis
from .power_meter.base import VoxelPowerMeter
from .rotation_axis.base import VoxelRotationAxis

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

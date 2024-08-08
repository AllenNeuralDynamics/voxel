"""
Available laser devices:
- voxel.devices.lasers.simulated
    - SimulatedLaser
- voxel.devices.lasers.vortran
    - StradusLaser
- voxel.devices.lasers.cobolt
    - SkyraLaser
- voxel.devices.lasers.oxxius
    -  OxxiusLBXLaser
    -  OxxiusLCXLaser
- voxel.devices.lasers.coherent
    - ObisLXLaser
    - ObisLSLaser
    - GenesisMXLaser
"""

from .base import BaseLaser

__all__ = ['BaseLaser']

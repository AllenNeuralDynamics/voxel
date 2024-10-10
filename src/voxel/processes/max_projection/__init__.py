"""
Available max projection processes:
- voxel.processes.max_projection.cpu.max_projection
    - CPUMaxProjection
- voxel.processes.max_projection.gpu.max_projection
    - GPUMaxProjection
"""

from .base import BaseMaxProjection
from voxel.processes.max_projection.cpu.numpy import CPUMaxProjection
from voxel.processes.max_projection.gpu.pyclesperanto import GPUMaxProjection

__all__ = [
    "BaseMaxProjection",
    "CPUMaxProjection",
    "GPUMaxProjection"
]

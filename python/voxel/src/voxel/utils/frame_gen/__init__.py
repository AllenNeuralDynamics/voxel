from voxel.utils.frame_gen.base import FrameGenerator

from .reference import TileReferenceGenerator, UpsampleReferenceGenerator
from .synthetic import CheckeredGenerator, RippleGenerator, SpiralGenerator

__all__ = [
    'CheckeredGenerator',
    'FrameGenerator',
    'RippleGenerator',
    'SpiralGenerator',
    'TileReferenceGenerator',
    'UpsampleReferenceGenerator',
]

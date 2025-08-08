from voxel.utils.frame_gen.base import FrameGenerator
from .synthetic import RippleGenerator, SpiralGenerator, CheckeredGenerator
from .reference import UpsampleReferenceGenerator, TileReferenceGenerator


__all__ = [
    "RippleGenerator",
    "SpiralGenerator",
    "CheckeredGenerator",
    "UpsampleReferenceGenerator",
    "TileReferenceGenerator",
    "FrameGenerator",
]

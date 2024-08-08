"""
This module provides voxel compatible classes for AOTF modulated lasers.
"""
from .aotf_laser import AOTFLaser
from .aaopto import AOTF as AAOptoLaser

__all__ = [
    'AOTFLaser',
    'AAOptoLaser'
]
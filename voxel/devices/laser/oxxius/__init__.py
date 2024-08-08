"""
This module provides voxel compatible classes for Oxxius lasers.
Oxxius: https://www.oxxius.com/
"""

from .oxxius_lbx import OxxiusLBXLaser
from .oxxius_lcx import OxxiusLCXLaser

__all__ = [
    'OxxiusLBXLaser',
    'OxxiusLCXLaser'
]

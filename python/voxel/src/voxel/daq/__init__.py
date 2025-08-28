"""This package provides the core Data Acquisition (DAQ) functionality for the voxel module.

Modules:
    base (BaseDaq): Contains the base class for DAQ implementations.
Exports:
    BaseDaq: The primary base class for DAQ operations.

"""

from .base import BaseDaq

__all__ = ['BaseDaq']

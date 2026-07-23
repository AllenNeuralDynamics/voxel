"""On-demand digital-output devices.

The public API addresses logical lines with Boolean states. Physical port layout,
line grouping, and task allocation remain driver-specific.
"""

from .base import (
    OnDemandDO,
    OnDemandDOController,
    OnDemandDOHandle,
)
from .ni import NiOnDemandDO
from .simulated import SimulatedOnDemandDO

__all__ = [
    "NiOnDemandDO",
    "OnDemandDO",
    "OnDemandDOController",
    "OnDemandDOHandle",
    "SimulatedOnDemandDO",
]

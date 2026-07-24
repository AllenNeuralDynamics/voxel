"""On-demand analog and digital output devices.

The public APIs address logical voltage ports or Boolean lines. Physical layout,
grouping, and task allocation remain driver-specific.
"""

from .base import (
    OnDemandAO,
    OnDemandAOController,
    OnDemandAOHandle,
    OnDemandDO,
    OnDemandDOController,
    OnDemandDOHandle,
)

__all__ = [
    "OnDemandAO",
    "OnDemandAOController",
    "OnDemandAOHandle",
    "OnDemandDO",
    "OnDemandDOController",
    "OnDemandDOHandle",
]

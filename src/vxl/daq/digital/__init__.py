"""On-demand digital-output devices.

The public API addresses logical lines with Boolean states. Physical port layout,
line grouping, and task allocation remain driver-specific.
"""

from .base import (
    DigitalOnDemandOutput,
    DigitalOnDemandOutputController,
    DigitalOnDemandOutputHandle,
)
from .ni import NiDigitalOnDemandOutput
from .simulated import SimulatedDigitalOnDemandOutput

__all__ = [
    "DigitalOnDemandOutput",
    "DigitalOnDemandOutputController",
    "DigitalOnDemandOutputHandle",
    "NiDigitalOnDemandOutput",
    "SimulatedDigitalOnDemandOutput",
]

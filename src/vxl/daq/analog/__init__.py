"""Analog-output devices — clocked and on-demand.

Both drive voltage. Clocked (``AO``) is hardware-timed; on-demand
(``OnDemandAO``) is untimed / software-paced.
The shared card hubs live in ``vxl.daq.hub_ni`` / ``vxl.daq.hub_sim``.

Public surface:
  - ``AO`` / ``OnDemandAO`` — abstract driver bases.
  - ``*Controller`` — orchestration (clocked owns a state machine; on-demand is stateless).
  - ``*Handle`` — typed async clients used by application code.
  - ``AOSignals`` — declarative signal configuration (clocked).
  - ``Simulated*AO`` — in-memory stand-ins for tests/local runs.
  - ``Ni*AO`` — NI-DAQmx drivers.
"""

from .base import (
    AO,
    AOController,
    AOHandle,
    AOState,
    OnDemandAO,
    OnDemandAOController,
    OnDemandAOHandle,
)
from .models import AOSignals, DerivedResolutionError, resolve_to_arrays
from .ni import NiAO, NiOnDemandAO
from .simulated import SimulatedAO, SimulatedOnDemandAO

__all__ = [
    "AO",
    "AOController",
    "AOHandle",
    "AOSignals",
    "AOState",
    "DerivedResolutionError",
    "NiAO",
    "NiOnDemandAO",
    "OnDemandAO",
    "OnDemandAOController",
    "OnDemandAOHandle",
    "SimulatedAO",
    "SimulatedOnDemandAO",
    "resolve_to_arrays",
]

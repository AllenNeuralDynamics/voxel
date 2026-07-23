"""Analog-output devices — clocked and on-demand.

Both drive voltage. Clocked (``AnalogOutput``) is hardware-timed by an internal or
external sample clock; on-demand (``AnalogOnDemandOutput``) is untimed / software-paced.
The shared card hubs live in ``vxl.daq.hub_ni`` / ``vxl.daq.hub_sim``.

Public surface:
  - ``AnalogOutput`` / ``AnalogOnDemandOutput`` — abstract driver bases.
  - ``*Controller`` — orchestration (clocked owns a state machine; on-demand is stateless).
  - ``*Handle`` — typed async clients used by application code.
  - ``AOSignals`` + ``ClockSource`` variants — declarative signal configuration (clocked).
  - ``SimulatedAnalog*`` — in-memory stand-ins for tests/local runs.
  - ``NiAnalog*`` — NI-DAQmx drivers.
"""

from .base import (
    AnalogOnDemandOutput,
    AnalogOnDemandOutputController,
    AnalogOnDemandOutputHandle,
    AnalogOutput,
    AnalogOutputController,
    AnalogOutputHandle,
    AOState,
)
from .models import AOSignals, ClockSource, DerivedResolutionError, ExternalClock, InternalClock, resolve_to_arrays
from .ni import NiAnalogOnDemandOutput, NiAnalogOutput
from .simulated import SimulatedAnalogOnDemandOutput, SimulatedAnalogOutput

__all__ = [
    "AOSignals",
    "AOState",
    "AnalogOnDemandOutput",
    "AnalogOnDemandOutputController",
    "AnalogOnDemandOutputHandle",
    "AnalogOutput",
    "AnalogOutputController",
    "AnalogOutputHandle",
    "ClockSource",
    "DerivedResolutionError",
    "ExternalClock",
    "InternalClock",
    "NiAnalogOnDemandOutput",
    "NiAnalogOutput",
    "SimulatedAnalogOnDemandOutput",
    "SimulatedAnalogOutput",
    "resolve_to_arrays",
]

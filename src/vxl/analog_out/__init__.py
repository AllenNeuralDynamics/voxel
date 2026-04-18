"""Analog-output device abstractions for Voxel.

Replaces the ``vxl.daq`` API. See ``notes/RETHINKING_DAQ_API.md`` for background.

Public surface:
  - ``AnalogOutput`` — abstract driver base (vendor-specific subclasses implement primitives).
  - ``AnalogOutputController`` — vendor-agnostic orchestration (state machine, validation, diffing).
  - ``AnalogOutputHandle`` — typed async client used by application code.
  - ``AOSignals`` + ``ClockSource`` variants — declarative signal configuration.
  - ``SimulatedAnalogOutput`` / ``SimulatedDaqmx`` — in-memory stand-ins for tests/local runs.
  - ``NiAnalogOutput`` / ``NiDaqmx`` — NI-DAQmx driver + hub.
"""

from .base import (
    AnalogOutput,
    AnalogOutputController,
    AnalogOutputHandle,
    AOState,
    DerivedResolutionError,
    resolve_to_arrays,
)
from .models import AOSignals, ClockSource, ExternalClock, InternalClock
from .ni import NiAnalogOutput, NiDaqmx
from .simulated import SimulatedAnalogOutput, SimulatedDaqmx

__all__ = [
    "AOSignals",
    "AOState",
    "AnalogOutput",
    "AnalogOutputController",
    "AnalogOutputHandle",
    "ClockSource",
    "DerivedResolutionError",
    "ExternalClock",
    "InternalClock",
    "NiAnalogOutput",
    "NiDaqmx",
    "SimulatedAnalogOutput",
    "SimulatedDaqmx",
    "resolve_to_arrays",
]

"""DAQ interface module for Voxel systems."""

# TODO — follow up before trusting SyncTask.apply_unsafe (see vxl/daq/sync.py).
# Today apply_unsafe bets on NI-DAQmx defaults; before flipping it on in prod,
# the driver API needs these two items to turn the bet into an explicit contract:
#
#   1. Make AO regeneration mode explicit. Add set_regeneration_mode(enabled)
#      to the AOTask ABC, plumb through handle + controller, implement in the
#      NI and simulated drivers, and call it during SyncTask._build_scaffold.
#      Today we silently inherit NI-DAQmx's AllowRegeneration default.
#
#   2. Document AOTask.write's running-state contract. Either tighten the
#      docstring ("legal on a running task iff regeneration is allowed") or
#      split into write() (requires stopped) and write_live() (requires running)
#      so intent is visible at the API boundary.
#
# Non-blocking cleanup, worth doing but not required for apply_unsafe:
#   - Expose DaqTask.status through DaqHandle so callers can query running
#     state instead of mirroring it locally (see SyncTask._running).
#   - Add AO buffer introspection (samples_written, space_available) for
#     underrun diagnosis.
#   - Document illegal state transitions in the ABC (start-while-running,
#     write-after-close, etc.) — currently driver-defined.

from .base import AcqSampleMode, AOTask, COTask, DaqTask, PinInfo, TaskInfo, TaskStatus, VoxelDaq
from .controller import DaqController
from .handle import DaqHandle
from .sync import FrameTiming, SyncTask
from .wave import Waveform

__all__ = [
    "AOTask",
    "AcqSampleMode",
    "COTask",
    "DaqController",
    "DaqHandle",
    "DaqTask",
    "FrameTiming",
    "PinInfo",
    "SyncTask",
    "TaskInfo",
    "TaskStatus",
    "VoxelDaq",
    "Waveform",
]

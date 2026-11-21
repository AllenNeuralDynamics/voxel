"""Scan controller: the hardware timing master for one TDI strip pass.

On the BARSeq rig this is the ACS XY controller. One pass moves the scan axis across a strip at constant
velocity while the controller drives every gate (frame grabbers, camera line trigger, laser power, Z ramp).

Skeleton: the contract is in place; the bodies are TODO.
"""

import logging
from typing import ClassVar

from rigup import Device, describe
from seqsweep.devices.base import SeqSweepDeviceType
from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig


class ScanController(Device):
    """Vendor-neutral timing master for strip passes.

    ``gate_outputs`` maps laser IDs to controller power-gate outputs, so a ``ScanPassConfig`` can name lasers
    without knowing the wiring.
    """

    __DEVICE_TYPE__: ClassVar[str] = SeqSweepDeviceType.SCAN_CONTROLLER

    def __init__(self, uid: str, *, gate_outputs: dict[str, str]) -> None:
        super().__init__(uid=uid)
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._gate_outputs = dict(gate_outputs)

    @property
    @describe(label="Running", desc="Whether a pass is in progress", stream=True)
    def is_running(self) -> bool:
        # TODO: report the controller's motion/program state
        return False

    @describe(label="Configure Scan", desc="Load pass geometry and gating")
    def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        # TODO: check lasers against gate_outputs, program the controller
        pass

    @describe(label="Run Pass", desc="Start one strip pass in the given direction")
    def run(self, direction: ScanDirection) -> None:
        # TODO: start the pass without blocking
        pass

    @describe(label="Move To", desc="Move to an absolute (X, Y) position in mm; returns once the move has started")
    def move_to(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        # TODO: start the positioning move; None: the controller's configured positioning speed
        pass

    @describe(label="Move By", desc="Move by a relative (X, Y) step in mm; returns once the move has started")
    def move_by(self, dx_mm: float, dy_mm: float) -> None:
        # TODO: start the relative move
        pass

    @describe(label="Go Home", desc="Move to the configured origin")
    def go_home(self) -> None:
        # TODO: start the move to the origin
        pass

    @describe(label="Wait Motion End", desc="Block until both axes have settled")
    def wait_motion_end(self) -> None:
        # TODO: block until motion stops
        pass

    @describe(label="Read Status", desc="Per-axis position, motor state and faults")
    def read_status(self) -> dict[str, dict[str, float | bool | int]]:
        # TODO: report the axes
        return {}

    @describe(label="Abort", desc="Stop the pass and close every gate")
    def abort(self) -> None:
        # TODO: halt motion and close every gate; must be safe when idle
        pass

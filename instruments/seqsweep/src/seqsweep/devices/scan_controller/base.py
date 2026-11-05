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

    @describe(label="Abort", desc="Stop the pass and close every gate")
    def abort(self) -> None:
        # TODO: halt motion and close every gate; must be safe when idle
        pass

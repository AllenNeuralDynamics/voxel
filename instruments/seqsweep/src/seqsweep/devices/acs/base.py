"""Scan controller: the hardware timing master for one TDI strip pass.

On the BARSeq rig this is the ACS XY controller. One pass moves the scan axis across a strip at constant
velocity while the controller drives every gate (frame grabbers, camera line trigger, laser power, Z ramp).

Skeleton: the contract is in place; the bodies are TODO.
"""

from enum import StrEnum
from typing import ClassVar

from pydantic import Field
from vxlib.schema import FrozenModel

from rigup import Device, describe


class ScanDirection(StrEnum):
    FORWARD = "forward"  # start_um → end_um
    REVERSE = "reverse"  # end_um → start_um


class ScanPassConfig(FrozenModel):
    """One strip pass along the scan axis (µm, µm/s)."""

    start_um: float
    end_um: float
    velocity_um_s: float = Field(gt=0)
    line_pitch_um: float = Field(gt=0, description="Stage travel per camera line trigger")
    lasers: list[str] = Field(default_factory=list, description="Lasers gated on during the pass")


class ScanController(Device):
    """Vendor-neutral timing master for strip passes.

    ``gate_outputs`` maps laser IDs to controller power-gate outputs, so a ``ScanPassConfig`` can name lasers
    without knowing the wiring.
    """

    __DEVICE_TYPE__: ClassVar[str] = "scan_controller"

    def __init__(self, uid: str, *, gate_outputs: dict[str, str]) -> None:
        super().__init__(uid=uid)
        self._gate_outputs = dict(gate_outputs)

    @property
    @describe(label="Running", desc="Whether a pass is in progress", stream=True)
    def is_running(self) -> bool:
        # TODO: report the controller's motion/program state
        return False

    @describe(label="Configure Scan", desc="Load pass geometry and gating")
    def configure(self, config: ScanPassConfig) -> None:
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

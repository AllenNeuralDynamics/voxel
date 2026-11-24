"""Scan controller: the hardware timing master for one TDI strip pass.

On the BARSeq rig this is the ACS XY controller. One pass moves the scan axis across a strip at constant
velocity while the controller drives every gate (frame grabbers, camera line trigger, laser power, Z ramp).

Abstract contract: a subclass must implement every abstract method below or it cannot be built.
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from rigup import Device, describe
from seqsweep.devices.base import SeqSweepDeviceType
from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig


class XYPosition(BaseModel, frozen=True):
    """Feedback position of the stage in mm."""

    x: float
    y: float


class AxisStatus(BaseModel, frozen=True):
    """Motor state and faults of one axis."""

    enabled: bool
    in_position: bool
    moving: bool
    accelerating: bool
    fault: int
    motor_error: int


class StageStatus(BaseModel, frozen=True):
    """Motor state and faults of both axes."""

    x: AxisStatus
    y: AxisStatus


class ScanController(Device, ABC):
    """Vendor-neutral timing master for strip passes.

    ``ABC`` is listed explicitly: rigup's ``Device`` is a plain class, so without it ``@abstractmethod`` is not enforced.
    """

    __DEVICE_TYPE__: ClassVar[str] = SeqSweepDeviceType.SCAN_CONTROLLER

    def __init__(self, uid: str, *, move_velocity_mm_s: float, motion_timeout_s: float) -> None:
        super().__init__(uid=uid)
        if move_velocity_mm_s <= 0 or motion_timeout_s <= 0:
            raise ValueError("move_velocity_mm_s and motion_timeout_s must be positive")
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._move_velocity_mm_s = move_velocity_mm_s
        self._motion_timeout_s = motion_timeout_s

    @property
    @describe(label="Move speed", desc="Speed of positioning moves in mm/s, not the scan speed")
    def move_velocity_mm_s(self) -> float:
        return self._move_velocity_mm_s

    @property
    @describe(label="Motion timeout", desc="Give up waiting for a move to end after this many seconds")
    def motion_timeout_s(self) -> float:
        return self._motion_timeout_s

    @property
    @abstractmethod
    @describe(label="Running", desc="Whether a pass, the home move or any axis motion is in progress", stream=True)
    def is_running(self) -> bool:
        """True while a pass or the home program runs, or an axis moves."""

    @describe(label="Configure Scan", desc="Load pass geometry and gating")
    @abstractmethod
    def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        """Load the pass geometry and gating into the controller."""

    @describe(label="Run Pass", desc="Start one strip pass in the given direction")
    @abstractmethod
    def run(self, direction: ScanDirection) -> None:
        """Start the pass without blocking."""

    @describe(label="Move To", desc="Move to an absolute (X, Y) position in mm; returns once the move has started")
    @abstractmethod
    def move_abs(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        """Start the positioning move; ``velocity_mm_s`` None uses the current axis velocity."""

    @describe(label="Move By", desc="Move by a relative (X, Y) step in mm; returns once the move has started")
    @abstractmethod
    def move_rel(self, dx_mm: float, dy_mm: float) -> None:
        """Start the relative move."""

    @describe(label="Go Home", desc="Move to the home position; returns once the move has started")
    @abstractmethod
    def go_home(self) -> None:
        """Start the move to the home position."""

    @property
    @abstractmethod
    @describe(label="Position", desc="Feedback position in mm", units="mm", stream=True)
    def position_mm(self) -> XYPosition:
        """Current (X, Y) feedback position."""

    @describe(label="Read Status", desc="Per-axis motor state and faults")
    @abstractmethod
    def read_status(self) -> StageStatus:
        """Motor state and faults of the X and Y axes."""

    @describe(label="Abort", desc="Stop the pass and close every gate")
    @abstractmethod
    def abort(self) -> None:
        """Halt motion and close every gate; must be safe when idle."""

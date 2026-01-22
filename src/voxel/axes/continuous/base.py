"""Continuous axis abstraction for linear and rotational motion."""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from pyrig.device import DeviceController

from pyrig import describe
from voxel.axes.base import Axis
from voxel.device import DeviceType


class StepMode(StrEnum):
    """Standard stepping modes for TTL-triggered motion."""

    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class TriggerMode(StrEnum):
    """Standard trigger modes for step-and-shoot operations."""

    TTL = "ttl"  # External TTL triggers each step
    ONE_SHOT = "one_shot"  # Execute buffer once
    REPEATING = "repeating"  # Execute buffer repeatedly


class TTLStepperConfig(BaseModel, frozen=True):
    """Base configuration for TTL stepping operations.

    Attributes:
        step_mode: Whether steps are absolute or relative positions.
        trigger_mode: How the ring buffer should be triggered.
        pulse_after_move: Whether to send an output pulse after each step completes.
    """

    step_mode: StepMode
    trigger_mode: TriggerMode = TriggerMode.TTL
    pulse_after_move: bool = True


class TTLStepper(ABC):
    """Abstract capability for an axis that can be stepped by TTL pulses."""

    @abstractmethod
    def configure(self, cfg: TTLStepperConfig | Any) -> None:
        """Configure the hardware for a step-and-shoot operation.

        Args:
            cfg: Step-and-shoot configuration parameters. Accepts TTLStepperConfig
                or hardware-specific configuration types.
        """

    @abstractmethod
    def queue_absolute_move(self, position: float) -> None:
        """Queue an absolute move to the ring buffer.

        Args:
            position: Target absolute position in axis units.
        """

    @abstractmethod
    def queue_relative_move(self, delta: float) -> None:
        """Queue a relative move to the ring buffer.

        Args:
            delta: Relative distance to move in axis units.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset the step-and-shoot configuration and clear the buffer."""


class ContinuousAxis(Axis):
    """Base class for continuous motion axes (linear or rotational).

    This abstraction unifies linear and rotational axes by using generic
    property names with a `units` property to indicate the unit type
    (e.g., "mm" for linear, "deg" for rotational).

    Implementations must provide:
        - units: The unit string (e.g., "mm", "deg")
        - position: Current position in `units`
        - is_moving: Whether the axis is currently in motion
        - Motion commands: move_abs, move_rel, go_home, halt, await_movement
        - Calibration: set_zero_here, set_logical_position
        - Limits: upper_limit, lower_limit
        - Kinematics: speed, acceleration (optional: backlash, home)
    """

    __DEVICE_TYPE__ = DeviceType.CONTINUOUS_AXIS

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)

    # Unit specification _____________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Units", desc="Unit string for position values (e.g., 'mm', 'deg').")
    def units(self) -> str:
        """Unit string for position values (e.g., 'mm', 'deg')."""
        ...

    # Motion commands ________________________________________________________________________________________________

    @describe(label="Move Absolute", desc="Move to an absolute position.")
    @abstractmethod
    def move_abs(self, position: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to an absolute position.

        Args:
            position: Target absolute position in axis units.
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Move Relative", desc="Move a relative distance.")
    @abstractmethod
    def move_rel(self, delta: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move a relative distance.

        Args:
            delta: Distance to move in axis units (positive or negative).
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Go Home", desc="Move to the home position.")
    @abstractmethod
    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to the home position.

        Args:
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Halt", desc="Emergency stop - halt all motion immediately.")
    @abstractmethod
    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""
        ...

    @describe(label="Await Movement", desc="Wait until the axis stops moving.")
    @abstractmethod
    def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait until the axis stops moving.

        Args:
            timeout_s: Maximum time to wait in seconds. None means wait indefinitely.
        """

    # State properties _______________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Position", desc="The current position.", stream=True)
    def position(self) -> float:
        """The current position in axis units."""
        ...

    @property
    @abstractmethod
    @describe(label="Is Moving", desc="Whether the axis is currently moving.", stream=True)
    def is_moving(self) -> bool:
        """Whether the axis is currently moving."""
        ...

    # Configuration and calibration __________________________________________________________________________________

    @describe(label="Set Zero Here", desc="Set the current position as zero.")
    @abstractmethod
    def set_zero_here(self) -> None:
        """Set the current position as zero."""
        ...

    @describe(label="Set Logical Position", desc="Set the logical position without moving.")
    @abstractmethod
    def set_logical_position(self, position: float) -> None:
        """Set the logical position without moving (for calibration).

        Args:
            position: The position value to assign to the current physical location.
        """

    @property
    @abstractmethod
    @describe(label="Upper Limit", desc="The upper position limit.", stream=True)
    def upper_limit(self) -> float:
        """The upper position limit in axis units."""
        ...

    @upper_limit.setter
    @abstractmethod
    def upper_limit(self, value: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Lower Limit", desc="The lower position limit.", stream=True)
    def lower_limit(self) -> float:
        """The lower position limit in axis units."""
        ...

    @lower_limit.setter
    @abstractmethod
    def lower_limit(self, value: float) -> None: ...

    # Kinematic parameters ___________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Speed", desc="The current speed.", stream=True)
    def speed(self) -> float | None:
        """The current speed in axis units per second."""
        ...

    @speed.setter
    @abstractmethod
    def speed(self, value: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Acceleration", desc="The current acceleration.", stream=True)
    def acceleration(self) -> float | None:
        """The current acceleration in axis units per second squared."""
        ...

    @acceleration.setter
    @abstractmethod
    def acceleration(self, value: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Backlash", desc="The backlash compensation value.")
    def backlash(self) -> float | None:
        """The backlash compensation value in axis units."""
        ...

    @backlash.setter
    @abstractmethod
    def backlash(self, value: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Home Position", desc="The home position.")
    def home(self) -> float | None:
        """The home position in axis units."""
        ...

    @home.setter
    @abstractmethod
    def home(self, position: float) -> None: ...

    # Capabilities ___________________________________________________________________________________________________

    def get_ttl_stepper(self) -> TTLStepper | None:
        """Return a TTLStepper capability object if supported, otherwise None.

        This is an optional capability for axes that support TTL-triggered stepping.

        Returns:
            TTLStepper instance if supported, None otherwise.
        """
        return None


# ==================== Continuous Axis Controller ====================


class ScanMode(StrEnum):
    IDLE = "IDLE"
    TTL_STEPPING = "TTL_STEPPING"


class ContinuousAxisController(DeviceController[ContinuousAxis]):
    """Controller for ContinuousAxis with TTL stepping support."""

    def __init__(self, device: ContinuousAxis, stream_interval: float = 0.5):
        super().__init__(device, stream_interval=stream_interval)
        self._scan_mode = ScanMode.IDLE
        self._ttl_stepper = device.get_ttl_stepper()

    @property
    @describe(label="Scan Mode", stream=True)
    def scan_mode(self) -> ScanMode:
        return self._scan_mode

    @property
    @describe(label="TTL Stepping Available")
    def ttl_stepping_available(self) -> bool:
        return self._ttl_stepper is not None

    @describe(label="Configure TTL Stepper")
    async def configure_ttl_stepper(self, cfg: TTLStepperConfig) -> None:
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")
        if self._scan_mode != ScanMode.IDLE:
            raise RuntimeError(f"Cannot configure TTL stepper while in {self._scan_mode} mode")

        await self._run_sync(self._ttl_stepper.configure, cfg)
        self._scan_mode = ScanMode.TTL_STEPPING

    @describe(label="Queue Absolute Move")
    async def queue_absolute_move(self, position: float) -> None:
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")
        if self._scan_mode != ScanMode.TTL_STEPPING:
            raise RuntimeError("TTL stepper not configured")

        await self._run_sync(self._ttl_stepper.queue_absolute_move, position)

    @describe(label="Queue Relative Move")
    async def queue_relative_move(self, delta: float) -> None:
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")
        if self._scan_mode != ScanMode.TTL_STEPPING:
            raise RuntimeError("TTL stepper not configured")

        await self._run_sync(self._ttl_stepper.queue_relative_move, delta)

    @describe(label="Reset TTL Stepper")
    async def reset_ttl_stepper(self) -> None:
        if not self._ttl_stepper:
            raise NotImplementedError(f"Axis {self.device.uid} does not support TTL stepping")

        await self._run_sync(self._ttl_stepper.reset)
        self._scan_mode = ScanMode.IDLE

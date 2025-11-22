from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from spim_rig.config import DeviceType

from pyrig import Device, describe


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
    def queue_absolute_move(self, position_mm: float) -> None:
        """Queue an absolute move to the ring buffer.

        Args:
            position_mm: Target absolute position in mm.
        """

    @abstractmethod
    def queue_relative_move(self, delta_mm: float) -> None:
        """Queue a relative move to the ring buffer.

        Args:
            delta_mm: Relative distance to move in mm.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset the step-and-shoot configuration and clear the buffer."""


class LinearAxis(Device):
    __DEVICE_TYPE__ = DeviceType.LINEAR_AXIS

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)

    # Motion commands ________________________________________________________________________________________________

    @describe(label="Move Absolute", desc="Move to an absolute position in mm.")
    @abstractmethod
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to an absolute position in mm.

        Args:
            pos_mm: Target absolute position in mm.
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Move Relative", desc="Move a relative distance in mm.")
    @abstractmethod
    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move a relative distance in mm.

        Args:
            delta_mm: Distance to move in mm (positive or negative).
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
    def halt(self) -> None: ...

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
    @describe(label="Position", units="mm", desc="The current position.", stream=True)
    def position_mm(self) -> float: ...

    @property
    @abstractmethod
    @describe(label="Is Moving", desc="Whether the axis is currently moving.", stream=True)
    def is_moving(self) -> bool: ...

    # Configuration and calibration __________________________________________________________________________________

    @describe(label="Set Zero Here", desc="Set the current position as zero.")
    @abstractmethod
    def set_zero_here(self) -> None: ...

    @describe(label="Set Logical Position", desc="Set the logical position without moving.")
    @abstractmethod
    def set_logical_position(self, pos_mm: float) -> None:
        """Set the logical position without moving (for calibration).

        Args:
            pos_mm: The position value to assign to the current physical location.
        """

    @property
    @abstractmethod
    @describe(label="Upper Limit", units="mm", desc="The upper position limit.", stream=True)
    def upper_limit_mm(self) -> float: ...

    @upper_limit_mm.setter
    @abstractmethod
    def upper_limit_mm(self, mm: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Lower Limit", units="mm", desc="The lower position limit.", stream=True)
    def lower_limit_mm(self) -> float: ...

    @lower_limit_mm.setter
    @abstractmethod
    def lower_limit_mm(self, mm: float) -> None: ...

    # Kinematic parameters ___________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Speed", units="mm/s", desc="The current speed.", stream=True)
    def speed_mm_s(self) -> float | None: ...

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, mm_per_s: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Acceleration", units="mm/s²", desc="The current acceleration.", stream=True)
    def acceleration_mm_s2(self) -> float | None: ...

    @acceleration_mm_s2.setter
    @abstractmethod
    def acceleration_mm_s2(self, mm_per_s2: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Backlash", units="mm", desc="The backlash compensation value.")
    def backlash_mm(self) -> float | None: ...

    @backlash_mm.setter
    @abstractmethod
    def backlash_mm(self, mm: float) -> None: ...

    @property
    @abstractmethod
    @describe(label="Home Position", units="mm", desc="The home position.")
    def home(self) -> float | None: ...

    @home.setter
    @abstractmethod
    def home(self, pos_mm: float) -> None: ...

    # Capabilities ___________________________________________________________________________________________________

    def get_ttl_stepper(self) -> TTLStepper | None:
        """Return a TTLStepper capability object if supported, otherwise None.

        This is an optional capability for axes that support TTL-triggered stepping.

        Returns:
            TTLStepper instance if supported, None otherwise.
        """
        return None

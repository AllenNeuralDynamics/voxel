from abc import abstractmethod

from spim_rig.device import DeviceType

from pyrig import Device, describe


class RotationAxis(Device):
    """Base class for rotational motion axes.

    Provides interface for continuous rotational motion control.
    """

    __DEVICE_TYPE__ = DeviceType.ROTATION_AXIS

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)

    # Motion commands ________________________________________________________________________________________________

    @describe(label="Rotate Absolute", desc="Rotate to an absolute angle in degrees")
    @abstractmethod
    def rotate_abs(self, angle_deg: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Rotate to an absolute angle in degrees.

        Args:
            angle_deg: Target absolute angle in degrees.
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Rotate Relative", desc="Rotate by a relative angle in degrees")
    @abstractmethod
    def rotate_rel(self, delta_deg: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Rotate by a relative angle in degrees.

        Args:
            delta_deg: Angle to rotate in degrees (positive or negative).
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Go Home", desc="Move to the home position")
    @abstractmethod
    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to the home position.

        Args:
            wait: If True, block until movement is complete.
            timeout_s: Maximum time to wait in seconds (only used if wait=True).
        """

    @describe(label="Halt", desc="Emergency stop - halt all motion immediately")
    @abstractmethod
    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""

    @describe(label="Await Movement", desc="Wait until the axis stops moving")
    @abstractmethod
    def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait until the axis stops moving.

        Args:
            timeout_s: Maximum time to wait in seconds. None means wait indefinitely.
        """

    # State properties _______________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Angle", units="deg", desc="The current angle.", stream=True)
    def angle_deg(self) -> float:
        """Current angle in degrees."""

    @property
    @abstractmethod
    @describe(label="Is Moving", desc="Whether the axis is currently moving.", stream=True)
    def is_moving(self) -> bool:
        """Whether the axis is currently moving."""

    # Configuration and calibration __________________________________________________________________________________

    @describe(label="Set Zero Here", desc="Set the current angle as zero")
    @abstractmethod
    def set_zero_here(self) -> None:
        """Set current angle as zero."""

    @describe(label="Set Logical Angle", desc="Set the logical angle without moving")
    @abstractmethod
    def set_logical_angle(self, angle_deg: float) -> None:
        """Set the logical angle without moving (for calibration).

        Args:
            angle_deg: The angle value to assign to the current physical position.
        """

    # Kinematic parameters ___________________________________________________________________________________________

    @property
    @abstractmethod
    @describe(label="Angular Speed", units="deg/s", desc="The current angular speed.", stream=True)
    def angular_speed_deg_s(self) -> float | None:
        """Current angular speed in degrees per second."""

    @angular_speed_deg_s.setter
    @abstractmethod
    def angular_speed_deg_s(self, deg_per_s: float) -> None:
        """Set angular speed in degrees per second."""

    @property
    @abstractmethod
    @describe(label="Angular Acceleration", units="deg/s²", desc="The current angular acceleration.")
    def angular_acceleration_deg_s2(self) -> float | None:
        """Current angular acceleration in degrees per second squared."""

    @angular_acceleration_deg_s2.setter
    @abstractmethod
    def angular_acceleration_deg_s2(self, deg_per_s2: float) -> None:
        """Set angular acceleration in degrees per second squared."""

    @property
    @abstractmethod
    @describe(label="Home Angle", units="deg", desc="The home angle.")
    def home(self) -> float | None:
        """Home angle in degrees."""

    @home.setter
    @abstractmethod
    def home(self, angle_deg: float) -> None:
        """Set home angle in degrees."""

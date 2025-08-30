from abc import abstractmethod

from exaspim_control.voxel_classic.devices.base import BaseDevice


class BaseStage(BaseDevice):
    """Base class for stage devices."""

    @abstractmethod
    def move_relative_mm(self, position: float, wait: bool = True) -> None:
        """Move the stage relative to its current position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """

    @abstractmethod
    def move_absolute_mm(self, position: float, wait: bool = True) -> None:
        """Move the stage to an absolute position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """

    @abstractmethod
    def start(self) -> None:
        """Start the stage."""

    @property
    @abstractmethod
    def position_mm(self) -> float | None:
        """Get the current position of the stage in millimeters.

        :return: Current position in millimeters
        :rtype: float | None
        """

    @property
    @abstractmethod
    def limits_mm(self) -> tuple[float, float]:
        """Get the limits of the stage in millimeters.

        :return: Limits in millimeters
        :rtype: tuple
        """

    @property
    @abstractmethod
    def backlash_mm(self) -> float:
        """Get the backlash of the stage in millimeters.

        :return: Backlash in millimeters
        :rtype: float
        """

    @backlash_mm.setter
    @abstractmethod
    def backlash_mm(self, backlash: float) -> None:
        """Set the backlash of the stage in millimeters.

        :param backlash: Backlash in millimeters
        :type backlash: float
        """

    @property
    @abstractmethod
    def speed_mm_s(self) -> float:
        """Get the speed of the stage in millimeters per second.

        :return: Speed in millimeters per second
        :rtype: float
        """

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, speed_mm_s: float) -> None:
        """Set the speed of the stage in millimeters per second.

        :param speed_mm_s: Speed in millimeters per second
        :type speed_mm_s: float
        """

    @property
    @abstractmethod
    def acceleration_ms(self) -> float:
        """Get the acceleration of the stage in millimeters per second squared.

        :return: Acceleration in millimeters per second squared
        :rtype: float
        """

    @acceleration_ms.setter
    @abstractmethod
    def acceleration_ms(self, acceleration: float) -> None:
        """Set the acceleration of the stage in millimeters per second squared.

        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """

    @property
    @abstractmethod
    def mode(self) -> str | int:
        """Get the mode of the stage.

        :return: Mode of the stage
        :rtype: int
        """

    @mode.setter
    @abstractmethod
    def mode(self, mode: str) -> None:
        """Set the mode of the stage.

        :param mode: Mode of the stage
        :type mode: int
        """

    @abstractmethod
    def is_axis_moving(self) -> bool:
        """Check if the axis is moving.

        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """

    @abstractmethod
    def zero_in_place(self) -> None:
        """Zero the stage in place."""

    @abstractmethod
    def close(self) -> None:
        """Close the stage."""

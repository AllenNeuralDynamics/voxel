import logging
import time

from voxel_classic.devices.stage.base import BaseStage

MODES = ["step shoot", "off", "stage scan"]


class SimulatedStage(BaseStage):
    """
    Simulated stage class for handling simulated stage devices.
    """

    def __init__(self, hardware_axis: str, instrument_axis: str) -> None:
        """
        Initialize the Stage object.

        :param hardware_axis: Hardware axis
        :type hardware_axis: str
        :param instrument_axis: Instrument axis
        :type instrument_axis: str
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._hardware_axis = hardware_axis.upper()
        self._instrument_axis = instrument_axis.lower()
        self.id = self.instrument_axis
        self._position_mm = 0
        self._speed_mm_s = 1.0
        self._limits_mm = [-10000, 10000]
        self._mode = "off"
        self._backlash_mm = 0.1
        self._acceleration_ms = 100.0

    def move_relative_mm(self, position: float, wait: bool = False) -> None:
        """
        Move the stage relative to its current position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to False
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"relative move by: {self.hardware_axis}={position} mm and {w_text}waiting.")
        move_time_s = position / self._speed_mm_s
        self.move_end_time_s = time.time() + move_time_s
        self._position_mm += position
        if wait:
            while time.time() < self.move_end_time_s:
                time.sleep(0.01)

    def move_absolute_mm(self, position: float, wait: bool = False) -> None:
        """
        Move the stage to an absolute position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to False
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"absolute move to: {self.hardware_axis}={position} mm and {w_text}waiting.")
        move_time_s = abs(self._position_mm - position) / self._speed_mm_s
        self.move_end_time_s = time.time() + move_time_s
        self._position_mm = position
        if wait:
            while time.time() < self.move_end_time_s:
                time.sleep(0.01)

    def setup_stage_scan(
        self,
        fast_axis_start_position: float,
        slow_axis_start_position: float,
        slow_axis_stop_position: float,
        frame_count: int,
        frame_interval_um: float,
        strip_count: int,
        pattern: str,
        retrace_speed_percent: int,
    ) -> None:
        """
        Setup a stage scan.

        :param fast_axis_start_position: Fast axis start position
        :type fast_axis_start_position: float
        :param slow_axis_start_position: Slow axis start position
        :type slow_axis_start_position: float
        :param slow_axis_stop_position: Slow axis stop position
        :type slow_axis_stop_position: float
        :param frame_count: Frame count
        :type frame_count: int
        :param frame_interval_um: Frame interval in micrometers
        :type frame_interval_um: float
        :param strip_count: Strip count
        :type strip_count: int
        :param pattern: Scan pattern
        :type pattern: str
        :param retrace_speed_percent: Retrace speed percent
        :type retrace_speed_percent: int
        """
        self._position_mm = fast_axis_start_position

    def halts(self) -> None:
        """
        Halt the stage.
        """
        pass

    @property
    def limits_mm(self) -> tuple[int, int]:
        """
        Get the limits of the stage in millimeters.

        :return: Limits in millimeters
        :rtype: tuple
        """
        return self._limits_mm[0], self._limits_mm[1]

    @property
    def position_mm(self) -> float:
        """
        Get the current position of the stage in millimeters.

        :return: Current position in millimeters
        :rtype: float
        """
        return self._position_mm

    @position_mm.setter
    def position_mm(self, value: float) -> None:
        """
        Set the current position of the stage in millimeters.

        :param value: Position in millimeters
        :type value: float
        """
        self._position_mm = value

    @property
    def speed_mm_s(self) -> float:
        """
        Get the speed of the stage in millimeters per second.

        :return: Speed in millimeters per second
        :rtype: float
        """
        return self._speed_mm_s

    @speed_mm_s.setter
    def speed_mm_s(self, speed_mm_s: float) -> None:
        """
        Set the speed of the stage in millimeters per second.

        :param speed_mm_s: Speed in millimeters per second
        :type speed_mm_s: float
        """
        self._speed_mm_s = speed_mm_s

    @property
    def backlash_mm(self) -> float:
        """
        Get the backlash of the stage in millimeters.

        :return: Backlash in millimeters
        :rtype: float
        """
        return self._backlash_mm

    @backlash_mm.setter
    def backlash_mm(self, backlash: float) -> None:
        """
        Set the backlash of the stage in millimeters.

        :param backlash: Backlash in millimeters
        :type backlash: float
        """
        self._backlash_mm = backlash
        self.log.info(f"set backlash to: {backlash} mm.")

    @property
    def acceleration_ms(self) -> dict[str, float]:
        """
        Get the acceleration of the stage in millimeters per second squared.

        :return: Acceleration in millimeters per second squared
        :rtype: dict[str, float]
        """
        return {self.instrument_axis.lower(): self._acceleration_ms}

    @acceleration_ms.setter
    def acceleration_ms(self, acceleration: float) -> None:
        """
        Set the acceleration of the stage in millimeters per second squared.

        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """
        self._acceleration_ms = acceleration
        self.log.info(f"set acceleration to: {acceleration} [ms].")

    @property
    def mode(self) -> str:
        """
        Get the mode of the stage.

        :return: Mode of the stage
        :rtype: str
        """
        return self._mode

    @mode.setter
    def mode(self, mode: str) -> None:
        """
        Set the mode of the stage.

        :param mode: Mode of the stage
        :type mode: str
        :raises ValueError: If mode is not valid
        """
        valid = MODES
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)
        self._mode = mode
        self.log.info(f"set mode to: {mode}.")

    @property
    def hardware_axis(self) -> str:
        """
        Get the hardware axis.

        :return: Hardware axis
        :rtype: str
        """
        return self._hardware_axis

    @property
    def instrument_axis(self) -> str:
        """
        Get the instrument axis.

        :return: Instrument axis
        :rtype: str
        """
        return self._instrument_axis

    def is_axis_moving(self) -> bool:
        """
        Check if the axis is moving.

        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """
        return time.time() < self.move_end_time_s

    def zero_in_place(self) -> None:
        """
        Zero the stage in place.
        """
        self.log.info("zeroing simulated stage.")
        self._position_mm = 0

    def close(self) -> None:
        """
        Close the stage.
        """
        self.log.info("closing simulated stage.")
        pass

    def start(self) -> None:
        """
        Start the stage.
        """
        self.log.info("starting simulated stage.")
        pass

    def setup_step_shoot_scan(self, step_size_um: float) -> None:
        """
        Setup a step shoot scan.

        :param step_size_um: Step size in micrometers
        :type step_size_um: float
        """
        self.log.info(f"setup step shoot scan with step size: {step_size_um} um.")
        pass

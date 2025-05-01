import threading
import time
import logging
from typing import Any, Callable, Dict, List

from tigerasi.device_codes import (RingBufferMode, ScanPattern, TTLIn0Mode,
                                   TTLOut0Mode)
from tigerasi.tiger_controller import TigerController as TigerBox

# globals

lock = threading.RLock()

# constants for Tiger ASI hardware

STEPS_PER_UM = 10
UPDATE_RATE_HZ = 1.0

MODES = {
    "step shoot": TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
    "off": TTLIn0Mode.OFF,
    "stage scan": TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION,
}

SCAN_PATTERN = {
    "raster": ScanPattern.RASTER,
    "serpentine": ScanPattern.SERPENTINE,
}

# decorators
def thread_locked(function: Callable) -> Callable:
    """
    Decorator to ensure that a function is executed with a thread lock.

    :param function: The function to be locked
    :type function: Callable
    :return: The wrapped function with locking
    :rtype: Callable
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Wrapper function to execute the original function with a lock.

        :param args: Positional arguments for the function
        :type args: Any
        :param kwargs: Keyword arguments for the function
        :type kwargs: Any
        :return: The result of the function execution
        :rtype: Any
        """
        with lock:
            return function(*args, **kwargs)
    return wrapper
    
class TigerController(TigerBox):
    """
    Controller for the ASI Tiger stage.
    """

    def __init__(self, com_port: str, log_level: str = "INFO",) -> None:
        """
        Initialize the TigerController object.

        :param com_port: COM port for the controller
        :type com_port: str
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        """
        super().__init__(com_port)
        for axis in self.ordered_axes:
            self.log.info(f"resetting ring buffer for axis={axis.upper()}")
            # clear ring buffer incase there are persistent values
            self.reset_ring_buffer(axis=axis.upper())
        self.position_mm_updater = PositionUpdater(tigerbox=self)

    def get_position_mm(self) -> float:
        """
        Get the current position in millimeters.

        :return: Current position in millimeters
        :rtype: float
        """
        return self.position_mm_updater.position_mm

    @thread_locked
    def move_relative_mm(self, axis: str, position: float, wait: bool = True) -> None:
        """
        Move the stage relative to its current position.

        :param axis: Hardware axis to move
        :type axis: str
        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"Relative move by: {axis}={position} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.move_relative(**{axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.is_axis_moving(axis):
                time.sleep(0.001)

    @thread_locked
    def move_absolute_mm(self, axis: str, position: float, wait: bool = True) -> None:
        """
        Move the stage to an absolute position.

        :param axis: Hardware axis to move
        :type axis: str
        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"Absolute move to: {axis}={position} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.move_absolute(**{axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.is_axis_moving(axis):
                time.sleep(0.001)

    @thread_locked
    def is_moving(self, axis: str) -> bool:
        """
        Check if the axis is moving.

        :param axis: Hardware axis to move
        :type axis: str
        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """
        return self.is_axis_moving(axis)
    
    @thread_locked
    def setup_stage_scan(
        self,
        fast_axis: str,
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

        :param fast_axis: Fast axis for scanning
        :type fast_axis: str
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
        :raises ValueError: If pattern is not valid or retrace speed percent is out of range
        """
        # TODO: if position is unspecified, we should set is as
        #  "current position" from hardware.
        # Get the axis id in machine coordinate frame.
        if self.get_mode() == "stage scan":
            valid_pattern = list(SCAN_PATTERN.keys())
            if pattern not in valid_pattern:
                raise ValueError("pattern must be one of %r." % valid_pattern)
            assert retrace_speed_percent <= 100 and retrace_speed_percent > 0
            axis_to_card = self.axis_to_card
            fast_card = axis_to_card[fast_axis][0]
            fast_position = axis_to_card[fast_axis][1]
            slow_axis = next(
                key for key, value in axis_to_card.items() if value[0] == fast_card and value[1] != fast_position
            )
            # Stop any existing scan. Apply machine coordinate frame scan params.
            self.log.debug(
                f"fast axis start: {fast_axis_start_position}," f"slow axis start: {slow_axis_start_position}"
            )
            self.setup_scan(
                fast_axis,
                slow_axis,
                pattern=SCAN_PATTERN[pattern],
            )
            self.scanr(
                scan_start_mm=fast_axis_start_position,
                pulse_interval_um=frame_interval_um,
                num_pixels=frame_count,
                retrace_speed_percent=retrace_speed_percent,
            )
            self.scanv(
                scan_start_mm=slow_axis_start_position, scan_stop_mm=slow_axis_stop_position, line_count=strip_count
            )
        else:
            raise ValueError(f"mode must be stage scan not {self.get_mode()}")

    @thread_locked
    def setup_step_shoot_scan(self, axis: str, step_size_um: float) -> None:
        """
        Setup a step shoot scan.

        :param axis: Axis to setup
        :type axis: str
        :param step_size_um: Step size in micrometers
        :type step_size_um: float
        """
        step_size_steps = step_size_um * STEPS_PER_UM
        self.reset_ring_buffer(axis=axis.upper())
        self.setup_ring_buffer(axis, mode=RingBufferMode.TTL)
        self.queue_buffered_move(**{axis: step_size_steps})
        # TTL mode dictates whether ring buffer move is relative or absolute.
        self.set_ttl_pin_modes(
            TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
            TTLOut0Mode.PULSE_AFTER_MOVING,
            aux_io_mode=0,
            aux_io_mask=0,
            aux_io_state=0,
        )

    @thread_locked
    def start(self) -> None:
        """
        Start the stage.
        """
        if self.get_mode() == "stage scan":
            self.start_scan()
        elif self.get_mode() == "step shoot":
            pass

    @thread_locked
    def get_limits_mm(self, axis: str) -> List[float]:
        """
        Get the limits of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :return: Limits in millimeters
        :rtype: List[float]
        """
        limit_lower = self.get_lower_travel_limit(axis)
        limit_upper = self.get_upper_travel_limit(axis)
        limits = [limit_lower, limit_upper]
        return limits

    @thread_locked
    def get_backlash_mm(self, axis: str) -> Dict[str, float]:
        """
        Get the backlash of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :return: Backlash in millimeters
        :rtype: Dict[str, float]
        """
        backlash = self.get_axis_backlash(axis)
        return backlash

    @thread_locked
    def set_backlash_mm(self, axis: str, backlash: float) -> None:
        """
        Set the backlash of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :param backlash: Backlash in millimeters
        :type backlash: float
        """
        self.set_axis_backlash(**{axis: backlash})

    @thread_locked
    def get_speed_mm_s(self, axis: str) -> Dict[str, float]:
        """
        Get the speed of the stage in millimeters per second.

        :param axis: Stage axis
        :type axis: str
        :return: Speed in millimeters per second
        :rtype: Dict[str, float]
        """
        speed = self.get_speed(axis)
        return speed

    @thread_locked
    def set_speed_mm_s(self, axis: str, speed: float) -> None:
        """
        Set the speed of the stage in millimeters per second.

        :param axis: Stage axis
        :type axis: str
        :param speed: Speed in millimeters per second
        :type speed: float
        """
        self.set_speed(**{axis: speed})

    @thread_locked
    def get_acceleration_ms(self, axis: str) -> Dict[str, float]:
        """
        Get the acceleration of the stage in millimeters per second squared.

        :param axis: Stage axis
        :type axis: str
        :return: Acceleration in millimeters per second squared
        :rtype: Dict[str, float]
        """
        acceleration = self.get_acceleration(axis)
        return acceleration

    @thread_locked
    def set_acceleration_ms(self, axis: str, acceleration: float) -> None:
        """
        Set the acceleration of the stage in millimeters per second squared.

        :param axis: Stage axis
        :type axis: str
        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """
        self.set_acceleration(**{axis: acceleration})

    @thread_locked
    def get_mode(self, axis: str) -> str:
        """
        Get the mode of the stage.

        :param axis: Stage axis
        :type axis: str
        :return: Mode of the stage
        :rtype: str
        """
        card_address = self.axis_to_card[axis][0]
        ttl_reply = self.get_ttl_pin_modes(card_address)  # note this does not return ENUM values
        mode = int(ttl_reply[str.find(ttl_reply, "X") + 2 : str.find(ttl_reply, "Y") - 1])  # strip the X= response
        converted_mode = next(key for key, enum in MODES.items() if enum.value == mode)
        return converted_mode

    @thread_locked
    def set_mode(self, axis: str, mode: str) -> None:
        """
        Set the mode of the stage.

        :param axis: Stage axis
        :type axis: str
        :param mode: Mode of the stage
        :type mode: str
        :raises ValueError: If mode is not valid
        """
        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)
        card_address = self.axis_to_card[axis][0]
        self.set_ttl_pin_modes(in0_mode=MODES[mode], card_address=card_address)

    @thread_locked
    def halt_axis(self, axis: str) -> None:
        """
        Halt the stage axis.

        :param axis: Stage axis
        :type axis: str
        """
        self.halt()

    @thread_locked
    def zero_axis(self, axis: str) -> None:
        """
        Zero the stage in place.

        :param axis: Stage axis
        :type axis: str
        """
        self.zero_in_place(axis)

    @thread_locked
    def log_metadata(self, axis: str) -> None:
        """
        Log metadata.

        :param axis: Stage axis
        :type axis: str
        """
        self.log.info("tiger hardware axis parameters")
        build_config = self.get_build_config()
        self.log.debug(f"{build_config}")
        axis_settings = self.get_info(axis)
        for setting in axis_settings:
            self.log.info(f"{axis} axis, {setting}, {axis_settings[setting]}")

    @thread_locked
    def close(self) -> None:
        """
        Close the TigerController.
        """
        # stop the updating thread
        self.position_mm_updater.close()
        self.ser.close()


class PositionUpdater:
    """
    Class for continuously updating the stage positions in millimeters.
    """

    def __init__(self, tigerbox: TigerController, log_level: str = "INFO",) -> None:
        """
        Initialize the TigerController object.

        :param tigerbox: TigerController object.
        :type tigerbox: TigerController
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.log.setLevel(log_level)
        self.tigerbox = tigerbox
        self.get_positions = True
        # initialize positions in mm
        self.position_mm = {axis: 0.0 for axis in self.tigerbox.ordered_axes}
        self.position_mm_updater = threading.Thread(target=self.position_mm_updater, args=(lock,))
        self.position_mm_updater.start()

    def position_mm_updater(self, lock: threading.Lock) -> None:
        """
        Thread to continuously get the position in millimeters for all axes.
        """
        # get position for all axes on some time interval
        # returns a dict of {hardware axes: positions}
        while self.get_positions:
            with lock:
                try:
                    position_mm = self.tigerbox.get_position(*self.tigerbox.ordered_axes)
                    self.position_mm.update(position_mm)
                except:
                    self.log.error('could not update positions')
            time.sleep(1.0 / UPDATE_RATE_HZ)

    def close(self) -> None:
        """
        Close the position updater class.
        """
        self.get_positions = False

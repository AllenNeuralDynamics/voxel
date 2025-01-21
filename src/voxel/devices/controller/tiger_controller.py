import threading
import time

from typing import Dict, List
from tigerasi.device_codes import RingBufferMode, ScanPattern, TTLIn0Mode, TTLOut0Mode
from tigerasi.tiger_controller import TigerController as TigerBox

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


class TigerController(TigerBox):
    """
    Controller for the ASI Tiger stage.
    """

    def __init__(self, com_port: str) -> None:
        """
        Initialize the TigerController object.

        :param com_port: COM port for the controller
        :type com_port: str
        """
        super().__init__(com_port)
        for axis in self.ordered_axes:
            self.log.info(f"resetting ring buffer for axis={axis.upper()}")
            # clear ring buffer incase there are persistent values
            self.reset_ring_buffer(axis=axis.upper())
        self._position_mm_updater = PositionUpdater(self)

    def get_position_mm(self) -> float:
        """
        Get the current position in millimeters.

        :return: Current position in millimeters
        :rtype: float
        """
        return self._position_mm_updater._position_mm

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
            while self.is_moving():
                time.sleep(0.001)

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
            while self.is_moving():
                time.sleep(0.001)

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
        if self.mode == "stage scan":
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
            raise ValueError(f"mode must be stage scan not {self.mode}")

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

    def start(self) -> None:
        """
        Start the stage.
        """
        if self.mode == "stage scan":
            self.start_scan()
        elif self.mode == "step shoot":
            pass

    def get_limits_mm(self, axis: str) -> List[float]:
        """
        Get the limits of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :return: Limits in millimeters
        :rtype: List[float]
        """
        # Get lower/upper limit in tigerbox frame.
        tiger_limit_lower = self.get_lower_travel_limit(axis)
        tiger_limit_upper = self.get_upper_travel_limit(axis)
        limits = sorted([tiger_limit_lower, tiger_limit_upper])
        return limits

    def get_backlash_mm(self, axis: str) -> Dict[str, float]:
        """
        Get the backlash of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :return: Backlash in millimeters
        :rtype: Dict[str, float]
        """
        tiger_backlash = self.get_axis_backlash(axis)
        return tiger_backlash

    def set_backlash_mm(self, axis: str, backlash: float) -> None:
        """
        Set the backlash of the stage in millimeters.

        :param axis: Stage axis
        :type axis: str
        :param backlash: Backlash in millimeters
        :type backlash: float
        """
        self.tigerbox.set_axis_backlash(**{axis: backlash})

    def get_speed_mm_s(self, axis: str) -> Dict[str, float]:
        """
        Get the speed of the stage in millimeters per second.

        :param axis: Stage axis
        :type axis: str
        :return: Speed in millimeters per second
        :rtype: Dict[str, float]
        """
        tiger_speed = self.get_speed(axis)
        return tiger_speed

    def set_speed_mm_s(self, axis: str, speed: float) -> None:
        """
        Set the speed of the stage in millimeters per second.

        :param axis: Stage axis
        :type axis: str
        :param speed: Speed in millimeters per second
        :type speed: float
        """
        self.set_speed(**{axis: speed})

    from typing import Dict

    def get_acceleration_ms(self, axis: str) -> Dict[str, float]:
        """
        Get the acceleration of the stage in millimeters per second squared.

        :param axis: Stage axis
        :type axis: str
        :return: Acceleration in millimeters per second squared
        :rtype: Dict[str, float]
        """
        tiger_acceleration = self.get_acceleration(axis)
        return tiger_acceleration

    def set_acceleration_ms(self, axis: str, acceleration: float) -> None:
        """
        Set the acceleration of the stage in millimeters per second squared.

        :param axis: Stage axis
        :type axis: str
        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """
        self.set_acceleration(**{axis: acceleration})

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

    def halt(self) -> None:
        """
        Halt the stage.
        """
        self.halt()

    def is_axis_moving(self, axis: str) -> bool:
        """
        Check if the axis is moving.

        :param axis: Stage axis
        :type axis: str
        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """
        return self.is_axis_moving(axis)

    def zero_in_place(self, axis: str) -> None:
        """
        Zero the stage in place.

        :param axis: Stage axis
        :type axis: str
        """
        # We must populate the axes explicitly since the tigerbox is shared
        # between camera stage and sample stage.
        self.zero_in_place(axis)

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

    def close(self) -> None:
        """
        Close the TigerController.
        """
        # stop the updating thread
        print("closing")
        self._position_mm_updater.close()
        self.ser.close()


class PositionUpdater:
    """
    Class for continuously updating the stage positions in millimeters.
    """

    def __init__(self, tigerbox: TigerController) -> None:
        """
        Initialize the TigerController object.

        :param tigerbox: TigerController object.
        :type tigerbox: TigerController
        """
        self._tigerbox = tigerbox
        self._get_positions = True
        self._position_mm = 0  # internal cache of position values
        self._position_mm_updater = threading.Thread(target=self._position_mm_updater)
        self._position_mm_updater.start()

    def _position_mm_updater(self) -> None:
        """
        Thread to continuously get the position in millimeters for all axes.
        """
        # get position for all axes on some time interval
        # returns a dict of {hardware axes: positions}
        while self._get_positions:
            with threading.RLock():
                self._position_mm = self._tigerbox.get_position(*self._tigerbox.ordered_axes)
            time.sleep(1.0 / UPDATE_RATE_HZ)

    def close(self) -> None:
        """
        Close the position updater class.
        """
        self._get_positions = False

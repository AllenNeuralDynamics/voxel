import logging
from time import sleep
from typing import Dict, Optional

from tigerasi.device_codes import *

from voxel.devices.controller.asi.tiger import TigerController
from voxel.devices.stage.base import BaseStage

# constants for Tiger ASI hardware

STEPS_PER_UM = 10

MODES = {
    "step shoot": TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
    "off": TTLIn0Mode.OFF,
    "stage scan": TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION,
}

SCAN_PATTERN = {
    "raster": ScanPattern.RASTER,
    "serpentine": ScanPattern.SERPENTINE,
}

JOYSTICK_AXES = {
    "x joystick": JoystickInput.JOYSTICK_X,
    "y joystick": JoystickInput.JOYSTICK_Y,
    "z wheel": JoystickInput.Z_WHEEL,
    "f wheel": JoystickInput.F_WHEEL,
    "none": JoystickInput.NONE,
}

POLARITIES = {
    "inverted": JoystickPolarity.INVERTED,
    "default": JoystickPolarity.DEFAULT,
}


class TigerStage(BaseStage):
    """
    Stage class for handling ASI stage devices.
    """

    def __init__(
        self,
        tigerbox: TigerController,
        hardware_axis: str,
        instrument_axis: str,
        log_level: str = "INFO",
    ) -> None:
        """
        Initialize the Stage object.

        :param tigerbox: TigerController object
        :type tigerbox: TigerController
        :param hardware_axis: Hardware axis
        :type hardware_axis: str
        :param instrument_axis: Instrument axis
        :type instrument_axis: str
        :param log_level: Logging level, defaults to "INFO"
        :type log_level: str, optional
        :raises ValueError: If both tigerbox and port are None
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.log.setLevel(log_level)

        if tigerbox is None and port is None:
            raise ValueError("Tigerbox and port cannot both be none")

        self.tigerbox = tigerbox
        self.tigerbox.log.setLevel(log_level)

        self.hardware_axis = hardware_axis.upper()
        self.instrument_axis = instrument_axis.lower()
        self.id = instrument_axis.lower()  # for base device lookup

        # axis_map: dictionary representing the mapping from sample pose to tigerbox axis.
        # i.e: `axis_map[<sample_frame_axis>] = <tiger_frame_axis>`.
        axis_map = {self.instrument_axis: self.hardware_axis}
        # We assume a bijective axis mapping (one-to-one and onto).
        self.log.debug(
            "Remapping axes with the convention "
            "{'instrument axis': 'hardware axis'} "
            f"from the following dict: {axis_map}."
        )
        self.instrument_to_hardware_axis_map = self._sanitize_axis_map(axis_map)
        r_axis_map = dict(zip(axis_map.values(), axis_map.keys()))
        self.hardware_to_instrument_axis_map = self._sanitize_axis_map(r_axis_map)
        self.log.debug(f"New instrument to hardware axis mapping: " f"{self.instrument_to_hardware_axis_map}")
        self.log.debug(f"New hardware to instrument axis mapping: " f"{self.hardware_to_instrument_axis_map}")
        self._joystick_mapping = self.tigerbox.get_joystick_axis_mapping(self.hardware_axis)

        # clear ring buffer incase there are persistent values
        self.tigerbox.reset_ring_buffer(axis=self.hardware_axis.upper())
        self.mode = 'off'

        # set parameter values
        # (!!) these are hardcoded here and cannot
        # be queiried from the tigerbox
        self.min_speed_mm_s: float = 0.001
        self.max_speed_mm_s: float = 1.000
        self.step_speed_mm_s: float = 0.01
        self.min_acceleration_ms: int = 50
        self.max_acceleration_ms: int = 2000
        self.step_acceleration_ms: int = 10
        self.min_backlash_mm: float = 0
        self.max_backlash_mm: float = 1
        self.step_backlash_mm: float = 0.01

    def _sanitize_axis_map(self, axis_map: Dict[str, str]) -> Dict[str, str]:
        """
        Sanitize the axis map by moving negative signs off keys and onto values.

        :param axis_map: Axis map
        :type axis_map: Dict[str, str]
        :return: Sanitized axis map
        :rtype: Dict[str, str]
        """
        sanitized_axis_map = {}
        for axis, t_axis in axis_map.items():
            axis = axis.lower()
            t_axis = t_axis.lower()
            sign = "-" if axis.startswith("-") ^ t_axis.startswith("-") else ""
            sanitized_axis_map[axis.lstrip("-")] = f"{sign}{t_axis.lstrip('-')}"
        return sanitized_axis_map

    def _remap(self, axes: Dict[str, float], mapping: Dict[str, str]) -> Dict[str, float]:
        """
        Remap axes using the provided mapping.

        :param axes: Axes to remap
        :type axes: Dict[str, float]
        :param mapping: Mapping to use for remapping
        :type mapping: Dict[str, str]
        :return: Remapped axes
        :rtype: Dict[str, float]
        """
        new_axes = {}
        for axis, value in axes.items():
            axis = axis.lower()
            # Default to same axis if no remapped axis exists.
            new_axis = mapping.get(axis, axis)  # Get new key.
            negative = 1 if new_axis.startswith("-") else 0
            new_axes[new_axis.lstrip("-")] = (-1) ** negative * value  # Get new value.
        return new_axes

    def _instrument_to_hardware(self, axes: Dict[str, float]) -> Dict[str, float]:
        """
        Convert instrument axes to hardware axes.

        :param axes: Instrument axes
        :type axes: Dict[str, float]
        :return: Hardware axes
        :rtype: Dict[str, float]
        """
        return self._remap(axes, self.instrument_to_hardware_axis_map)

    def _instrument_to_hardware_axis_list(self, *axes: str) -> list[str]:
        """
        Convert instrument axes to hardware axes list.

        :param axes: Instrument axes
        :type axes: str
        :return: Hardware axes list
        :rtype: list[str]
        """
        # Easiest way to convert is to temporarily convert into dict.
        axes_dict = {x: 0 for x in axes}
        tiger_axes_dict = self._instrument_to_hardware(axes_dict)
        return list(tiger_axes_dict.keys())

    def _hardware_to_instrument(self, axes: Dict[str, float]) -> Dict[str, float]:
        """
        Convert hardware axes to instrument axes.

        :param axes: Hardware axes
        :type axes: Dict[str, float]
        :return: Instrument axes
        :rtype: Dict[str, float]
        """
        return self._remap(axes, self.hardware_to_instrument_axis_map)

    def move_relative_mm(self, position: float, wait: bool = True) -> None:
        """
        Move the stage relative to its current position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"Relative move by: {self.hardware_axis}={position:.3f} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.tigerbox.move_relative(**{self.hardware_axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.tigerbox.is_moving():
                sleep(0.001)

    def move_absolute_mm(self, position: float, wait: bool = True) -> None:
        """
        Move the stage to an absolute position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"Absolute move to: {self.hardware_axis}={position:.3f} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.tigerbox.move_absolute(**{self.hardware_axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.tigerbox.is_moving():
                sleep(0.001)

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
            fast_axis = self.hardware_axis
            axis_to_card = self.tigerbox.axis_to_card
            fast_card = axis_to_card[fast_axis][0]
            fast_position = axis_to_card[fast_axis][1]
            slow_axis = next(
                key for key, value in axis_to_card.items() if value[0] == fast_card and value[1] != fast_position
            )
            # Stop any existing scan. Apply machine coordinate frame scan params.
            self.log.debug(
                f"fast axis start: {fast_axis_start_position}," f"slow axis start: {slow_axis_start_position}"
            )
            self.tigerbox.setup_scan(
                fast_axis,
                slow_axis,
                pattern=SCAN_PATTERN[pattern],
            )
            self.tigerbox.scanr(
                scan_start_mm=fast_axis_start_position,
                pulse_interval_um=frame_interval_um,
                num_pixels=frame_count,
                retrace_speed_percent=retrace_speed_percent,
            )
            self.tigerbox.scanv(
                scan_start_mm=slow_axis_start_position, scan_stop_mm=slow_axis_stop_position, line_count=strip_count
            )
        else:
            raise ValueError(f"mode must be stage scan not {self.mode}")

    def setup_step_shoot_scan(self, step_size_um: float) -> None:
        """
        Setup a step shoot scan.

        :param step_size_um: Step size in micrometers
        :type step_size_um: float
        """
        step_size_steps = step_size_um * STEPS_PER_UM
        self.tigerbox.reset_ring_buffer(axis=self.hardware_axis.upper())
        self.tigerbox.setup_ring_buffer(self.hardware_axis, mode=RingBufferMode.TTL)
        self.tigerbox.queue_buffered_move(**{self.hardware_axis: step_size_steps})
        # TTL mode dictates whether ring buffer move is relative or absolute.
        self.tigerbox.set_ttl_pin_modes(
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
            self.tigerbox.start_scan()
        elif self.mode == "step shoot":
            pass

    def close(self) -> None:
        """
        Close the stage.
        """
        self.log.info("closing stage.")
        pass

    @property
    def joystick_axis(self) -> str:
        """
        Get the joystick axis.

        :return: Joystick axis
        :rtype: str
        """
        return next(key for key, enum in JOYSTICK_AXES.items() if enum.value == self._joystick_mapping)

    @joystick_axis.setter
    def joystick_axis(self, axis: str) -> None:
        """
        Set the joystick axis.

        :param axis: Joystick axis
        :type axis: str
        :raises ValueError: If axis is not valid
        """
        valid = list(JOYSTICK_AXES.keys())
        if axis not in valid:
            raise ValueError("joystick axis must be one of %r." % valid)
        self.tigerbox.bind_axis_to_joystick_input(**{self.hardware_axis: JOYSTICK_AXES[axis]})
        self._joystick_mapping = JOYSTICK_AXES[axis]

    @property
    def position_mm(self) -> Optional[float]:
        """
        Get the current position of the stage in millimeters.

        :return: Current position in millimeters
        :rtype: Optional[float]
        """
        position_dict = self.tigerbox.get_position_mm()
        tiger_position = position_dict[self.hardware_axis]
        # converting 1/10 um to mm
        tiger_position_mm = tiger_position / 10000
        return tiger_position_mm

    @position_mm.setter
    def position_mm(self, value: float) -> None:
        """
        Set the current position of the stage in millimeters.

        :param value: Position in millimeters
        :type value: float
        """
        self.move_absolute_mm(value, False)

    @property
    def limits_mm(self) -> list[float]:
        """
        Get the limits of the stage in millimeters.

        :return: Limits in millimeters
        :rtype: list[float]
        """
        # Get lower/upper limit in tigerbox frame.
        tiger_limit_lower = self.tigerbox.get_lower_travel_limit(self.hardware_axis)
        tiger_limit_upper = self.tigerbox.get_upper_travel_limit(self.hardware_axis)
        # Convert to sample frame before returning.
        sample_limit_lower = list(self._hardware_to_instrument(tiger_limit_lower).values())[0]
        sample_limit_upper = list(self._hardware_to_instrument(tiger_limit_upper).values())[0]
        limits = sorted([sample_limit_lower, sample_limit_upper])
        return limits

    @property
    def backlash_mm(self) -> Dict[str, float]:
        """
        Get the backlash of the stage in millimeters.

        :return: Backlash in millimeters
        :rtype: Dict[str, float]
        """
        tiger_backlash = self.tigerbox.get_axis_backlash(self.hardware_axis)
        return self._hardware_to_instrument(tiger_backlash)

    @backlash_mm.setter
    def backlash_mm(self, backlash: float) -> None:
        """
        Set the backlash of the stage in millimeters.

        :param backlash: Backlash in millimeters
        :type backlash: float
        """
        self.tigerbox.set_axis_backlash(**{self.hardware_axis: backlash})

    @property
    def speed_mm_s(self) -> Dict[str, float]:
        """
        Get the speed of the stage in millimeters per second.

        :return: Speed in millimeters per second
        :rtype: Dict[str, float]
        """
        tiger_speed = self.tigerbox.get_speed(self.hardware_axis)
        return self._hardware_to_instrument(tiger_speed)

    @speed_mm_s.setter
    def speed_mm_s(self, speed: float) -> None:
        """
        Set the speed of the stage in millimeters per second.

        :param speed: Speed in millimeters per second
        :type speed: float
        """
        self.tigerbox.set_speed(**{self.hardware_axis: speed})

    @property
    def acceleration_ms(self) -> Dict[str, float]:
        """
        Get the acceleration of the stage in millimeters per second squared.

        :return: Acceleration in millimeters per second squared
        :rtype: Dict[str, float]
        """
        tiger_acceleration = self.tigerbox.get_acceleration(self.hardware_axis)
        return self._hardware_to_instrument(tiger_acceleration)

    @acceleration_ms.setter
    def acceleration_ms(self, acceleration: float) -> None:
        """
        Set the acceleration of the stage in millimeters per second squared.

        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """
        self.tigerbox.set_acceleration(**{self.hardware_axis: acceleration})

    @property
    def mode(self) -> str:
        """
        Get the mode of the stage.

        :return: Mode of the stage
        :rtype: str
        """
        card_address = self.tigerbox.axis_to_card[self.hardware_axis][0]
        ttl_reply = self.tigerbox.get_ttl_pin_modes(card_address)  # note this does not return ENUM values
        mode = int(ttl_reply[str.find(ttl_reply, "X") + 2 : str.find(ttl_reply, "Y") - 1])  # strip the X= response
        converted_mode = next(key for key, enum in MODES.items() if enum.value == mode)
        return converted_mode

    @mode.setter
    def mode(self, mode: str) -> None:
        """
        Set the mode of the stage.

        :param mode: Mode of the stage
        :type mode: str
        :raises ValueError: If mode is not valid
        """
        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)

        card_address = self.tigerbox.axis_to_card[self.hardware_axis][0]
        self.tigerbox.set_ttl_pin_modes(in0_mode=MODES[mode], card_address=card_address)

    def halt(self) -> None:
        """
        Halt the stage.
        """
        self.tigerbox.halt()

    def is_axis_moving(self) -> bool:
        """
        Check if the axis is moving.

        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """
        return self.tigerbox.is_axis_moving(self.hardware_axis)

    def zero_in_place(self) -> None:
        """
        Zero the stage in place.
        """
        # We must populate the axes explicitly since the tigerbox is shared
        # between camera stage and sample stage.
        self.tigerbox.zero_in_place(self.hardware_axis)

    def log_metadata(self) -> None:
        """
        Log metadata.
        """
        self.log.info("tiger hardware axis parameters")
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f"{build_config}")
        axis_settings = self.tigerbox.get_info(self.hardware_axis)
        self.log.info("{'instrument axis': 'hardware axis'} " f"{self.instrument_to_hardware_axis_map}.")
        for setting in axis_settings:
            self.log.info(f"{self.hardware_axis} axis, {setting}, {axis_settings[setting]}")

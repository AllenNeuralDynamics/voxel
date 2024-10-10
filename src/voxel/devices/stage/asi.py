import logging
from voxel.devices.utils.singleton import Singleton
from voxel.devices.stage.base import BaseStage
from tigerasi.tiger_controller import TigerController, STEPS_PER_UM
from tigerasi.device_codes import *
from time import sleep

# constants for Tiger ASI hardware

STEPS_PER_UM = 10

MODES = {
    "step shoot": TTLIn0Mode.REPEAT_LAST_REL_MOVE,
    "off": TTLIn0Mode.OFF,
    "stage scan": TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION
}

SCAN_PATTERN = {
    "raster": ScanPattern.RASTER,
    "serpentine": ScanPattern.SERPENTINE,
}


# singleton wrapper around TigerController
class TigerControllerSingleton(TigerController, metaclass=Singleton):
    def __init__(self, com_port):
        super(TigerControllerSingleton, self).__init__(com_port)


class Stage(BaseStage):

    def __init__(self, hardware_axis: str, instrument_axis: str, tigerbox: TigerController = None, port: str = None,
                 log_level="INFO"):
        """Connect to hardware.

        :param tigerbox: TigerController instance.
        :param hardware_axis: stage hardware axis.
        :param instrument_axis: instrument hardware axis.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.log.setLevel(log_level)

        if tigerbox == None and port == None:
            raise ValueError('Tigerbox and port cannot both be none')

        self.tigerbox = TigerControllerSingleton(com_port=port) if tigerbox is None else tigerbox
        self.tigerbox.log.setLevel(log_level)

        self._hardware_axis = hardware_axis.upper()
        self._instrument_axis = instrument_axis.lower()
        # TODO change this, but self.id for consistency in lookup
        self.id = self.instrument_axis
        # axis_map: dictionary representing the mapping from sample pose to tigerbox axis.
        # i.e: `axis_map[<sample_frame_axis>] = <tiger_frame_axis>`.
        axis_map = {self.instrument_axis: self.hardware_axis}
        # We assume a bijective axis mapping (one-to-one and onto).
        self.log.debug("Remapping axes with the convention "
                       "{'instrument axis': 'hardware axis'} "
                       f"from the following dict: {axis_map}.")
        self.instrument_to_hardware_axis_map = self._sanitize_axis_map(axis_map)
        r_axis_map = dict(zip(axis_map.values(), axis_map.keys()))
        self.hardware_to_instrument_axis_map = self._sanitize_axis_map(r_axis_map)
        self.log.debug(f"New instrument to hardware axis mapping: "
                       f"{self.instrument_to_hardware_axis_map}")
        self.log.debug(f"New hardware to instrument axis mapping: "
                       f"{self.hardware_to_instrument_axis_map}")
        self.tiger_joystick_mapping = self.tigerbox.get_joystick_axis_mapping()

        # set parameter values
        # (!!) these are hardcoded here and cannot
        # be queiried from the tigerbox
        self.min_speed_mm_s = 0.001
        self.max_speed_mm_s = 1.000
        self.step_speed_mm_s = 0.01
        self.min_acceleration_ms = 50
        self.max_acceleration_ms = 2000
        self.step_acceleration_ms = 10
        self.min_backlash_mm = 0
        self.max_backlash_mm = 1
        self.step_backlash_mm = 0.01

    def _sanitize_axis_map(self, axis_map: dict):
        """save an input axis mapping to apply to move commands.

        :param axis_map: dict, where the key (str) is the desired coordinate
            axis and the value (str) is the underlying machine coordinate axis.
            Note that the value may be signed, i.e: '-y'.
        """
        # Move negative signs off keys and onto values.
        sanitized_axis_map = {}
        for axis, t_axis in axis_map.items():
            axis = axis.lower()
            t_axis = t_axis.lower()
            sign = "-" if axis.startswith("-") ^ t_axis.startswith("-") else ""
            sanitized_axis_map[axis.lstrip("-")] = f"{sign}{t_axis.lstrip('-')}"
        return sanitized_axis_map

    def _remap(self, axes: dict, mapping: dict):
        """remap input axes to their corresponding output axes.

        Input axes is the desired coordinate frame convention;
        output axes are the axes as interpreted by the underlying hardware.

        :returns: either: a list of axes remapped to the new names
            or a dict of moves with the keys remapped to the underlying
            underlying hardware axes and the values unchanged.
        """
        new_axes = {}
        for axis, value in axes.items():
            axis = axis.lower()
            # Default to same axis if no remapped axis exists.
            new_axis = mapping.get(axis, axis)  # Get new key.
            negative = 1 if new_axis.startswith('-') else 0
            new_axes[new_axis.lstrip('-')] = (-1) ** negative * value  # Get new value.
        return new_axes

    def _instrument_to_hardware(self, axes: dict):
        """Remap a position or position delta specified in the sample frame to
        the tiger frame.

        :return: a dict of the position or position delta specified in the
            tiger frame
        """
        return self._remap(axes, self.instrument_to_hardware_axis_map)

    def _instrument_to_hardware_axis_list(self, *axes):
        """Return the axis specified in the sample frame to axis in the tiger
        frame. Minus signs are omitted."""
        # Easiest way to convert is to temporarily convert into dict.
        axes_dict = {x: 0 for x in axes}
        tiger_axes_dict = self._instrument_to_hardware(axes_dict)
        return list(tiger_axes_dict.keys())

    def _hardware_to_instrument(self, axes: dict):
        """Remap a position or position delta specified in the tiger frame to
        the sample frame.

        :return: a dict of the position or position delta specified in the
            sample frame
        """
        return self._remap(axes, self.hardware_to_instrument_axis_map)

    def move_relative_mm(self, position: float, wait: bool = True):
        w_text = "" if wait else "NOT "
        self.log.info(f"Relative move by: {self.hardware_axis}={position} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.tigerbox.move_relative(**{self.hardware_axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.tigerbox.is_moving():
                sleep(0.001)

    def move_absolute_mm(self, position: float, wait: bool = True):
        """Move the specified axes by their corresponding amounts.

        :param wait: If true, wait for the stage to arrive to the specified
            location. If false, (1) do not wait for the chars to exit the
            serial port, (2) do not wait for stage to respond, and
            (3) do not wait for the stage to arrive at the specified location.
        :param position: float, keyed by axis of which axis to move and by how much.
        """
        w_text = "" if wait else "NOT "
        self.log.info(f"Absolute move to: {self.hardware_axis}={position} mm and {w_text}waiting.")
        # convert from mm to 1/10um
        self.tigerbox.move_absolute(**{self.hardware_axis: round(position * 1000 * STEPS_PER_UM, 1)}, wait=wait)
        if wait:
            while self.tigerbox.is_moving():
                sleep(0.001)

    def setup_stage_scan(self, fast_axis_start_position: float,
                         slow_axis_start_position: float,
                         slow_axis_stop_position: float,
                         frame_count: int, frame_interval_um: float,
                         strip_count: int, pattern: str,
                         retrace_speed_percent: int):
        """Setup a stage scan orchestrated by the device hardware.

        This function sets up the outputting of <tile_count> output pulses
        spaced out by every <tile_interval_um> encoder counts.

        :param fast_axis: the axis to move along to take tile images.
        :param slow_axis: the axis to move across to take tile stacks.
        :param fast_axis_start_position:
        :param slow_axis_start_position:
        :param slow_axis_stop_position:
        :param frame_count: number of TTL pulses to fire.
        :param frame_interval_um: distance to travel between firing TTL pulses.
        :param strip_count: number of stacks to collect along the slow axis.
        """
        # TODO: if position is unspecified, we should set is as
        #  "current position" from hardware.
        # Get the axis id in machine coordinate frame.
        if self.mode == 'stage scan':
            valid_pattern = list(SCAN_PATTERN.keys())
            if pattern not in valid_pattern:
                raise ValueError("pattern must be one of %r." % valid_pattern)
            assert retrace_speed_percent <= 100 and retrace_speed_percent > 0
            fast_axis = self.hardware_axis
            axis_to_card = self.tigerbox.axis_to_card
            fast_card = axis_to_card[fast_axis][0]
            fast_position = axis_to_card[fast_axis][1]
            slow_axis = next(
                key for key, value in axis_to_card.items() if value[0] == fast_card and value[1] != fast_position)
            # Stop any existing scan. Apply machine coordinate frame scan params.
            self.log.debug(f"fast axis start: {fast_axis_start_position},"
                           f"slow axis start: {slow_axis_start_position}")
            self.tigerbox.setup_scan(fast_axis, slow_axis,
                                     pattern=SCAN_PATTERN[pattern], )
            self.tigerbox.scanr(scan_start_mm=fast_axis_start_position,
                                pulse_interval_um=frame_interval_um,
                                num_pixels=frame_count,
                                retrace_speed_percent=retrace_speed_percent)
            self.tigerbox.scanv(scan_start_mm=slow_axis_start_position,
                                scan_stop_mm=slow_axis_stop_position,
                                line_count=strip_count)
        else:
            raise ValueError(f'mode must be stage scan not {self.mode}')

    def setup_step_shoot_scan(self, step_size_um: float):
        """Queue a single-axis relative move of the specified amount."""
        step_size_steps = step_size_um * STEPS_PER_UM
        self.tigerbox.reset_ring_buffer()
        self.tigerbox.setup_ring_buffer(self.hardware_axis, mode=RingBufferMode.TTL)
        self.tigerbox.queue_buffered_move(**{self.hardware_axis: step_size_steps})
        # TTL mode dictates whether ring buffer move is relative or absolute.
        self.tigerbox.set_ttl_pin_modes(TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
                                        TTLOut0Mode.PULSE_AFTER_MOVING,
                                        aux_io_mode=0, aux_io_mask=0,
                                        aux_io_state=0)
        
    def start(self):
        """initiate a finite tile scan that has already been setup with
        :meth:`setup_finite_tile_scan`."""
        if self.mode == 'stage scan':
            self.tigerbox.start_scan()
        elif self.mode == 'step shoot':
            pass

    def close(self):
        self.tigerbox.ser.close()

    @property
    def position_mm(self):
        tiger_position = self.tigerbox.get_position(self.hardware_axis)
        # converting 1/10 um to mm
        tiger_position_mm = {k: v / 10000 for k, v in tiger_position.items()}
        # FIXME: Sometimes tigerbox yields empty stage position so return None if this happens?
        return self._hardware_to_instrument(tiger_position_mm).get(self.instrument_axis, None)

    @position_mm.setter
    def position_mm(self, value):
        self.move_absolute_mm(value, False)

    @property
    def limits_mm(self):
        """ Get the travel limits for the specified axes returns um.

        :return: 2-value lists, where the first element is the lower
            travel limit and the second element is the upper travel limit.
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
    def backlash_mm(self):
        """Get the axis backlash compensation."""
        tiger_backlash = self.tigerbox.get_axis_backlash(self.hardware_axis)
        return self._hardware_to_instrument(tiger_backlash)
    
    @backlash_mm.setter
    def backlash_mm(self, backlash: float):
        """Set the axis backlash compensation to a set value (0 to disable)."""
        self.tigerbox.set_axis_backlash(**{self.hardware_axis: backlash})

    @property
    def speed_mm_s(self):
        """Get the tiger axis speed."""
        tiger_speed = self.tigerbox.get_speed(self.hardware_axis)
        return self._hardware_to_instrument(tiger_speed)

    @speed_mm_s.setter
    def speed_mm_s(self, speed: float):
        self.tigerbox.set_speed(**{self.hardware_axis: speed})

    @property
    def acceleration_ms(self):
        """Get the tiger axis acceleration."""
        tiger_acceleration = self.tigerbox.get_acceleration(self.hardware_axis)
        return self._hardware_to_instrument(tiger_acceleration)
    
    @acceleration_ms.setter
    def acceleration_ms(self, acceleration: float):
        """Set the tiger axis acceleration."""
        self.tigerbox.set_acceleration(**{self.hardware_axis: acceleration})

    @property
    def mode(self):
        """Get the tiger axis ttl."""
        card_address = self.tigerbox.axis_to_card[self.hardware_axis][0]
        ttl_reply = self.tigerbox.get_ttl_pin_modes(card_address)  # note this does not return ENUM values
        mode = int(ttl_reply[str.find(ttl_reply, 'X') + 2:str.find(ttl_reply, 'Y') - 1])  # strip the X= response
        converted_mode = next(key for key, enum in MODES.items() if enum.value == mode)
        return converted_mode

    @mode.setter
    def mode(self, mode: str):
        """Set the tiger axis ttl."""

        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)

        card_address = self.tigerbox.axis_to_card[self.hardware_axis][0]
        self.tigerbox.set_ttl_pin_modes(in0_mode=MODES[mode], card_address=card_address)

    def halt(self):
        """Stop stage"""
        self.tigerbox.halt()

    def is_axis_moving(self):
        return self.tigerbox.is_axis_moving(self.hardware_axis)

    def zero_in_place(self):
        """set the specified axes to zero or all as zero if none specified."""
        # We must populate the axes explicitly since the tigerbox is shared
        # between camera stage and sample stage.
        self.tigerbox.zero_in_place(self.hardware_axis)

    def log_metadata(self):
        self.log.info('tiger hardware axis parameters')
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f'{build_config}')
        axis_settings = self.tigerbox.get_info(self.hardware_axis)
        self.log.info("{'instrument axis': 'hardware axis'} "
                      f"{self.instrument_to_hardware_axis_map}.")
        for setting in axis_settings:
            self.log.info(f'{self.hardware_axis} axis, {setting}, {axis_settings[setting]}')

    @property
    def hardware_axis(self):
        return self._hardware_axis

    @property
    def instrument_axis(self, ):
        return self._instrument_axis

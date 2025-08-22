from enum import StrEnum
from typing import Any, Literal

from tigerasi.device_codes import (
    JoystickInput,
    JoystickPolarity,
    ScanPattern,
    TTLIn0Mode,
    TTLOut0Mode,
)
from tigerasi.tiger_controller import TigerController
from voxel.devices import VoxelDevice, VoxelDeviceConnectionError, VoxelDeviceType
from voxel.devices.interfaces.linear_axis import LinearAxisDimension, ScanState

type AxisMap = dict[str, str]  # axis name -> hardware_axis
type JoystickMap = dict[str, str]  # axis name -> joystick axis
type DimensionsMap = dict[LinearAxisDimension, str]  # LinearAxisDimension -> axis name


class TigerBoxETLControlMode(StrEnum):
    TG1000_INPUT_NO_TEMP_COMPENSATION = '0'
    EXTERNAL_INPUT_NO_TEMP_COMPENSATION = '1'
    TG1000_INPUT_WITH_TEMP_COMPENSATION = '2'


STEPS_PER_UM = 10


class ASITigerBox(VoxelDevice):
    def __init__(self, port: str, name: str = 'tigerbox') -> None:
        super().__init__(name, device_type=VoxelDeviceType.HUB)
        self.tiger_controller = TigerController(port)
        self.axis_map = {}
        self.dimensions_map = {}
        self.scan_state = ScanState.IDLE

        # set parameter values
        # (!!) these are hardcoded here and cannot
        # be queiried from the tigerbox
        # TODO: Verify these values and use them in axis drivers
        self.axis_min_speed_mm_s = 0.001
        self.axis_max_speed_mm_s = 1.000
        self.axis_step_speed_mm_s = 0.01
        self.axis_min_acceleration_ms = 50
        self.axis_max_acceleration_ms = 2000
        self.axis_step_acceleration_ms = 10
        self.axis_min_backlash_mm = 0
        self.axis_max_backlash_mm = 1
        self.axis_step_backlash_mm = 0.01

        self.log = self.tiger_controller.log
        self.log.debug('Connected to TigerBox on port %s. Hardware Configuration: %s', port, self.build_config)

    @property
    def hardware_axes(self) -> list[str]:
        return self.tiger_controller.ordered_axes

    @property
    def build_config(self) -> dict[str, Any]:
        return self.tiger_controller.get_build_config()

    @property
    def joystick_mapping(self) -> dict[str, JoystickInput]:
        hardware_mapping = self.tiger_controller.get_joystick_axis_mapping()
        return {axis_name: hardware_mapping[hardware_axis] for axis_name, hardware_axis in self.axis_map.items()}

    def register_device(self, axis_name: str, hardware_axis: str) -> None:
        """Register a device with the TigerBox controller.

        :param axis_name: unique axis identifier
        :param hardware_axis: hardware axis name, must be one of the available axes on the connected TigerBox
        :raises VoxelDeviceConnectionError: if the hardware axis is not found in the connected TigerBox
        or if the axis ID is already registered.
        """
        if hardware_axis not in self.hardware_axes:
            msg = (
                f'Hardware axis {hardware_axis} not found in the connected tigerbox. '
                f'Available axes: {self.hardware_axes}'
            )
            raise VoxelDeviceConnectionError(
                msg,
            )

        for axis, hw_axis in self.axis_map.items():
            if hw_axis == hardware_axis:
                msg = f'Hardware axis {hardware_axis} already registered as {axis}'
                raise VoxelDeviceConnectionError(msg)
            if axis_name == axis:
                msg = f'Axis ID {axis_name} already registered as {hw_axis}'
                raise VoxelDeviceConnectionError(msg)

        self.axis_map[axis_name] = hardware_axis

    def register_linear_axis(
        self,
        axis_name: str,
        hardware_axis: str,
        dimension: LinearAxisDimension,
        joystick_polarity: Literal[-1, 1] = 1,
        joystick_input: JoystickInput = JoystickInput.NONE,
    ) -> None:
        """Register a linear axis with the TigerBox controller.

        :param axis_name: unique axis identifier
        :param hardware_axis: hardware axis name, must be one of the available axes on the connected TigerBox
        :param dimension: LinearAxisDimension, X, Y, Z, or N
        :param joystick_input: JoystickInput, the joystick input to bind to this axis
        :param joystick_polarity: 1 for DEFAULT, -1 for INVERTED
        :raises VoxelDeviceConnectionError: if the hardware axis is not found in the connected TigerBox
        or if the axis ID is already registered.
        """
        self.register_device(axis_name, hardware_axis)

        # there can be only one X, Y, Z axis but multiple N axes
        if dimension != LinearAxisDimension.N:
            if dimension in self.dimensions_map:
                msg = f'Dimension {dimension} already registered as {self.dimensions_map[dimension]}'
                raise ValueError(msg)
            self.dimensions_map[dimension] = axis_name

        joystick_input = joystick_input or self._default_joystick_input(dimension)
        if joystick_input != JoystickInput.NONE:
            self.tiger_controller.bind_axis_to_joystick_input(**{hardware_axis: joystick_input})
            polarity = JoystickPolarity.INVERTED if joystick_polarity < 0 else JoystickPolarity.DEFAULT
            self.tiger_controller.set_joystick_axis_polarity(**{hardware_axis: polarity})

        # self.disable_zero_button(axis_name)

    def deregister_device(self, axis_name: str) -> None:
        if axis_name in self.axis_map:
            self.axis_map.pop(axis_name)

        # Create a list of dimensions to remove
        dimensions_to_remove = [dimension for dimension, axis in self.dimensions_map.items() if axis == axis_name]

        # Remove the dimensions outside the loop
        for dimension in dimensions_to_remove:
            self.dimensions_map.pop(dimension)

    def close(self):
        if not self.axis_map:
            if self.scan_state == ScanState.SCANNING:
                self.tiger_controller.stop_scan()
            self.tiger_controller.ser.close() if self.tiger_controller.ser else None

    def get_axis_position(self, axis_name: str) -> float:
        box_axis = self.axis_map[axis_name]
        # steps = float(self.box.get_position(box_axis)[box_axis])
        steps = self.tiger_controller.get_position(box_axis)[box_axis]
        return steps / (STEPS_PER_UM * 1000)  # convert to mm

    def move_absolute_mm(self, axis_name: str, position_mm: float) -> None:
        self.tiger_controller.move_absolute(
            **{self.axis_map[axis_name]: round(position_mm * 1000 * STEPS_PER_UM)},
            wait=True,
        )

    def await_movement(self) -> None:
        self.tiger_controller.wait()

    def get_axis_limits(self, axis_name: str) -> tuple[float, float]:
        box_axis = self.axis_map[axis_name]
        lower = float(self.tiger_controller.get_lower_travel_limit(box_axis)[box_axis])
        upper = float(self.tiger_controller.get_upper_travel_limit(box_axis)[box_axis])
        return lower, upper

    def get_upper_travel_limit(self, axis_name: str) -> float:
        return float(self.tiger_controller.get_upper_travel_limit(self.axis_map[axis_name])[self.axis_map[axis_name]])

    def get_lower_travel_limit(self, axis_name: str) -> float:
        return float(self.tiger_controller.get_lower_travel_limit(self.axis_map[axis_name])[self.axis_map[axis_name]])

    def set_upper_travel_limit_in_place(self, axis_name: str):
        self.tiger_controller.set_upper_travel_limit(self.axis_map[axis_name])

    def set_lower_travel_limit_in_place(self, axis_name: str):
        self.tiger_controller.set_lower_travel_limit(self.axis_map[axis_name])

    def set_upper_travel_limit(self, axis_name: str, limit: float):
        self.tiger_controller.set_upper_travel_limit(**{self.axis_map[axis_name]: limit}, wait=True)

    def set_lower_travel_limit(self, axis_name: str, limit: float):
        self.tiger_controller.set_lower_travel_limit(**{self.axis_map[axis_name]: limit}, wait=True)

    def set_axis_limits(self, axis_name: str, lower_limit: float, upper_limit: float) -> None:
        self.set_upper_travel_limit(axis_name, upper_limit)
        self.set_lower_travel_limit(axis_name, lower_limit)

    def get_axis_speed(self, axis_name: str) -> float:
        box_axis = self.axis_map[axis_name]
        return float(self.tiger_controller.get_speed(box_axis)[box_axis])

    def set_axis_speed(self, axis_name: str, speed_mm_s: float) -> None:
        box_axis = self.axis_map[axis_name]
        self.tiger_controller.set_speed(**{box_axis: speed_mm_s}, wait=True)

    def get_axis_acceleration(self, axis_name: str) -> float:
        box_axis = self.axis_map[axis_name]
        return float(self.tiger_controller.get_acceleration(box_axis)[box_axis])

    def set_axis_acceleration(self, axis_name: str, acceleration_ms: float) -> None:
        box_axis = self.axis_map[axis_name]
        self.tiger_controller.set_acceleration(**{box_axis: acceleration_ms}, wait=True)

    def zero_in_place(self, axis_name: str) -> None:
        self.tiger_controller.zero_in_place(self.axis_map[axis_name])

    def get_axis_home_position(self, axis_name: str) -> float:
        res = self.tiger_controller.get_home(self.axis_map[axis_name])
        axis_home = res.get(self.axis_map[axis_name], 0.0)
        return float(axis_home)

    def set_axis_home_position(self, axis_name: str, position_mm: float | None = None) -> None:
        position_mm = position_mm or self.get_axis_position(axis_name)
        self.tiger_controller.set_home(**{self.axis_map[axis_name]: position_mm}, wait=True)

    def home(self, axis_name: str) -> None:
        self.tiger_controller.home(self.axis_map[axis_name])

    def is_axis_moving(self, axis_name: str) -> bool:
        return self.tiger_controller.are_axes_moving(self.axis_map[axis_name])[self.axis_map[axis_name]]

    # def get_axis_backlash(self, axis_name: str) -> float:
    #     box_axis = self.axis_map[axis_name]
    #     return float(self.box.get_axis_backlash(box_axis)[box_axis])

    def set_axis_backlash(self, axis_name: str, backlash_mm: float) -> None:
        box_axis = self.axis_map[axis_name]
        self.tiger_controller.set_axis_backlash(**{box_axis: backlash_mm}, wait=True)

    def setup_step_shoot_scan(self, axis_name: str, step_size_um: float) -> bool:
        """Queue a single-axis relative move of the specified amount."""
        if not self.has_all_stage_axes or self.dimensions_map[axis_name] != LinearAxisDimension.Z:
            return False
        try:
            if self.scan_state == ScanState.SCANNING:
                self.tiger_controller.stop_scan()
            step_size_steps = step_size_um * STEPS_PER_UM
            self.tiger_controller.reset_ring_buffer()
            self.tiger_controller.setup_ring_buffer(self.axis_map[axis_name])
            self.tiger_controller.queue_buffered_move(**{self.axis_map[axis_name]: step_size_steps}, wait=True)
            # TTL mode dictates whether ring buffer move is relative or absolute.
            self.tiger_controller.set_ttl_pin_modes(
                in0_mode=TTLIn0Mode.MOVE_TO_NEXT_REL_POSITION,
                out0_mode=TTLOut0Mode.PULSE_AFTER_MOVING,
                aux_io_mode=0,
                aux_io_mask=0,
                aux_io_state=0,
            )
            self.scan_state = ScanState.CONFIGURED
        except Exception:
            self.log.exception('Failed to setup step-and-shoot scan')
            return False
        else:
            return True

    # TODO Unfinished implementation of stage scan.
    def setup_stage_scan(
        self,
        fast_axis_start_position: float,
        slow_axis_start_position: float,
        slow_axis_stop_position: float,
        frame_count: int,
        frame_interval_um: float,
        strip_count: int,
        retrace_speed_percent: int,
        pattern: ScanPattern = ScanPattern.SERPENTINE,
    ):
        """Configure a stage scan orchestrated by the device hardware.

        This function sets up the outputting of <tile_count> output pulses
        spaced out by every <tile_interval_um> encoder counts.

        :param fast_axis_start_position:
        :param slow_axis_start_position:
        :param slow_axis_stop_position:
        :param frame_count: number of TTL pulses to fire.
        :param frame_interval_um: distance to travel between firing TTL pulses.
        :param strip_count: number of stacks to collect along the slow axis.
        :param retrace_speed_percent: speed of the retrace in percent of the scan speed.
        :param pattern:
        """
        # :param fast_axis: the axis to move along to take tile images.
        # :param slow_axis: the axis to move across to take tile stacks.
        # TODO: if position is unspecified, we should set is as
        #  "current position" from hardware.
        # Get the axis name in machine coordinate frame.
        max_retrace_speed_percent = 100
        if retrace_speed_percent <= 0 or retrace_speed_percent > max_retrace_speed_percent:
            msg = (
                f'Invalid retrace_speed_percent: {retrace_speed_percent}. '
                f'Must be between 1 and {max_retrace_speed_percent}.'
            )
            raise ValueError(msg)

        fast_axis = self.axis_map[LinearAxisDimension.X]
        slow_axis = self.axis_map[LinearAxisDimension.Y]

        # Stop any existing scan. Apply machine coordinate frame scan params.
        self.log.debug('fast axis start: %s, slow axis start: %s', fast_axis_start_position, slow_axis_start_position)

        self.tiger_controller.setup_scan(fast_axis, slow_axis, pattern)
        self.tiger_controller.scanr(
            scan_start_mm=fast_axis_start_position,
            pulse_interval_um=frame_interval_um,
            num_pixels=frame_count,
            retrace_speed_percent=retrace_speed_percent,
        )
        self.tiger_controller.scanv(
            scan_start_mm=slow_axis_start_position,
            scan_stop_mm=slow_axis_stop_position,
            line_count=strip_count,
        )

    def start_scan(self, wait: bool = True) -> None:
        if self.scan_state == ScanState.CONFIGURED:
            self.tiger_controller.start_scan(wait)
            self.scan_state = ScanState.SCANNING

    def stop_scan(self, wait: bool = True) -> None:
        self.tiger_controller.stop_scan(wait)
        self.scan_state = ScanState.IDLE

    @property
    def has_all_stage_axes(self) -> bool:
        return all(axis in self.dimensions_map for axis in LinearAxisDimension)

    def halt(self):
        """Stop all motion."""
        self.tiger_controller.halt()

    # Input Management ________________________________________________________________________________________________

    def bind_axis_to_joystick_input(self, axis_name: str, joystick_input: JoystickInput) -> None:
        """Bind a joystick input to the specified axis.

        Note: binding a tigerbox stage axis to a joystick input does not affect
        the direction of the input. To change the direction, you must use the
        physical DIP switches on the back of the Tigerbox card.

        Note: binding a tigerbox stage axis to a joystick input `also` enables
        it.

        :param axis_name: axis ID
        :param joystick_input: JoystickInput
        """
        self.tiger_controller.bind_axis_to_joystick_input(**{self.axis_map[axis_name]: joystick_input})

    def set_axis_joystick_polarity(self, axis_name: str, polarity: int) -> None:
        """Set the polarity of the joystick axis.
        :param axis_name: axis ID
        :param polarity: 1 for DEFAULT, -1 for INVERTED.
        """
        if polarity < 0:
            self.tiger_controller.set_joystick_axis_polarity(**{self.axis_map[axis_name]: JoystickPolarity.INVERTED})
        else:
            self.tiger_controller.set_joystick_axis_polarity(**{self.axis_map[axis_name]: JoystickPolarity.DEFAULT})

    def enable_axis_joystick_input(self, axis_name: str) -> None:
        """Enable the joystick input for the specified axis.
        :param axis_name: axis ID.
        """
        self.tiger_controller.enable_joystick_inputs(self.axis_map[axis_name])

    def disable_axis_joystick_input(self, axis_name: str) -> None:
        """Disable the joystick input for the specified axis.
        :param axis_name: axis ID.
        """
        self.tiger_controller.disable_joystick_inputs(self.axis_map[axis_name])

    # def disable_zero_button(self):
    #     """Disable the zero button functionality for all axes."""
    #     cmd_str = "BCA M=0"
    #     self.box.send(cmd_str)

    # def disable_zero_button(self, axis_name: str) -> None:
    #     """Disable the zero button for the specified axis.
    #     :param axis_name: axis ID
    #     """
    #     card = self.box.axis_to_card[self.axis_map[axis_name]][0]
    #     cmd_str = f"{card}BE M=0"
    #     self.box.send(cmd_str)
    #
    # def check_button_assignments(self):
    #     """Check button function assignments using the BE (BENABLE) command for all cards in the TigerController."""
    #     all_assignments = {}
    #
    #     # Get unique card addresses
    #     unique_cards = set(card for card, _ in self.box.axis_to_card.values())
    #
    #     for card in unique_cards:
    #         card_info = {}
    #
    #         # Construct the BE command
    #         cmd_str = f"{card}BE X? Y? Z? F? R? T? M?\r"
    #
    #         # Send the command and get the response
    #         response = self.box.send(cmd_str)
    #
    #         print(f"Raw response from card {card}: {response}")
    #
    #         # Parse the response
    #         if response.startswith(':'):
    #             parts = response[1:].split()  # Remove ':' and split
    #             for part in parts:
    #                 if '=' in part:
    #                     key, value = part.split('=')
    #                     try:
    #                         card_info[key] = int(value)
    #                     except ValueError:
    #                         card_info[key] = value  # Keep as string if not an integer
    #
    #         all_assignments[card] = card_info
    #
    #     return all_assignments

    # Tunable Lens ____________________________________________________________________________________________________
    def get_etl_temp(self, axis_name: str) -> float:
        return float(self.tiger_controller.get_etl_temp(self.axis_map[axis_name]))

    def get_axis_control_mode(self, axis_name: str) -> TigerBoxETLControlMode:
        return TigerBoxETLControlMode(self.tiger_controller.get_axis_control_mode(self.axis_map[axis_name]))

    def set_axis_control_mode(self, axis_name: str, mode: TigerBoxETLControlMode) -> None:
        self.tiger_controller.set_axis_control_mode(**{self.axis_map[axis_name]: mode}, wait=False)

    # Helpers _________________________________________________________________________________________________________
    def get_axis_info(self, axis_name: str) -> dict:
        return self.tiger_controller.get_info(self.axis_map[axis_name])

    @staticmethod
    def _default_joystick_input(dimension: LinearAxisDimension) -> JoystickInput:
        match dimension:
            case LinearAxisDimension.X:
                return JoystickInput.JOYSTICK_X
            case LinearAxisDimension.Y:
                return JoystickInput.JOYSTICK_Y
            case LinearAxisDimension.Z:
                return JoystickInput.Z_WHEEL
            case _:
                return JoystickInput.NONE

    @staticmethod
    def _sanitize_axis_map(axis_map: AxisMap) -> AxisMap:
        return {k: v.upper() for k, v in axis_map.items()}

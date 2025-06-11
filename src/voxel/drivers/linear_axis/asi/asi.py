from dataclasses import dataclass
from typing import Literal

from tigerasi.device_codes import JoystickInput as ASIJoystickInput

from voxel.devices.interfaces.linear_axis import LinearAxisDimension, ScanConfig, ScanState, VoxelLinearAxis
from voxel.drivers.hubs.tigerbox import ASITigerBox
from voxel.utils.descriptors.deliminated import deliminated_float


@dataclass
class ASITriggeredStepAndShootConfig(ScanConfig):
    start_mm: float
    stop_mm: float
    step_size_um: float


class ASITigerLinearAxis(VoxelLinearAxis):
    """ASI Tiger Linear Axis implementation.
    :param name: Unique identifier for the device
    :param hardware_axis: The hardware axis of the stage
    :param dimension: The dimension of the stage
    :param tigerbox: The ASITigerBox instance
    :param joystick_polarity: The polarity of the joystick input
    :param joystick_input: The joystick input to use
    :type name: str
    :type hardware_axis: str
    :type dimension: LinearAxisDimension
    :type tigerbox: ASITigerBox
    :type joystick_polarity: Literal[1, -1]
    :type joystick_input: ASIJoystickInput
    :raises DeviceConnectionError: If the stage with the specified hardware axis is not found or is already registered
    """

    def __init__(
        self,
        name: str,
        hardware_axis: str,
        dimension: LinearAxisDimension,
        tigerbox: ASITigerBox,
        joystick_polarity: Literal[1, -1] = 1,
        joystick_input: ASIJoystickInput = None,
    ):
        super().__init__(name, dimension)
        self._tigerbox = tigerbox
        self._hardware_axis = hardware_axis.upper()
        self._tigerbox.register_linear_axis(
            self.name, self._hardware_axis, self.dimension, joystick_polarity, joystick_input
        )

    def close(self):
        self._tigerbox.deregister_device(self.name)

    # Scanning properties and methods ________________________________________________________________________________

    def configure_scan(self, config: ScanConfig):
        if not self.dimension == LinearAxisDimension.Z:
            raise ValueError("Unable to configure scan. This axis is not used for scanning.")
        if config.scan_type == ScanConfig.ScanType.STEP_AND_SHOOT:
            self._tigerbox.setup_step_shoot_scan(self.name, config.step_size_um)
        elif config.scan_type == ScanConfig.ScanType.CONTINUOUS:
            self._log.warning("Continuous scans are not yet implemented.")

    def start_scan(self):
        if self.scan_state != ScanState.CONFIGURED:
            raise ValueError("Scan not configured. Call configure_scan first.")
        self._tigerbox.start_scan()

    def stop_scan(self):
        self._tigerbox.stop_scan()

    @property
    def scan_state(self) -> ScanState:
        return self._tigerbox.scan_state

    # Positional properties and methods ______________________________________________________________________________

    @deliminated_float(
        min_value=lambda self: self.lower_limit_mm,
        max_value=lambda self: self.upper_limit_mm,
    )
    def position_mm(self) -> float:
        return self._tigerbox.get_axis_position(self.name)

    @position_mm.setter
    def position_mm(self, value: float) -> None:
        self._tigerbox.move_absolute_mm(self.name, value)

    @property
    def upper_limit_mm(self) -> float:
        return self._tigerbox.get_upper_travel_limit(self.name)

    @upper_limit_mm.setter
    def upper_limit_mm(self, upper_limit_mm: float) -> None:
        self._tigerbox.set_upper_travel_limit(self.name, upper_limit_mm)

    def set_upper_limit_mm_in_place(self) -> None:
        self._tigerbox.set_upper_travel_limit_in_place(self.name)

    @property
    def lower_limit_mm(self) -> float:
        return self._tigerbox.get_lower_travel_limit(self.name)

    @lower_limit_mm.setter
    def lower_limit_mm(self, lower_limit_mm: float) -> None:
        self._tigerbox.set_lower_travel_limit(self.name, lower_limit_mm)

    def set_lower_limit_mm_in_place(self) -> None:
        self._tigerbox.set_lower_travel_limit_in_place(self.name)

    @property
    def is_moving(self) -> bool:
        return self._tigerbox.is_axis_moving(self.name)

    def await_movement(self):
        while self.is_moving:
            pass
        self._log.info(f"Axis {self.name} has stopped moving. Current position: {self.position_mm}")

    @property
    def home_position_mm(self) -> float:
        return self._tigerbox.get_axis_home_position(self.name)

    def set_home_position(self, home_position: float | None = None) -> None:
        """Set the home position of the axis
        :param home_position: The position to set as the home position.
        If None, the current position is set as the home position.
        """
        home_position = home_position or self.position_mm
        self._tigerbox.set_axis_home_position(self.name, home_position)

    def home(self, wait=False) -> None:
        """Move the axis to the home position."""
        self._tigerbox.home(self.name)
        if wait:
            self.await_movement()

    def zero_in_place(self) -> None:
        """Set the current position as the zero position"""
        return self._tigerbox.zero_in_place(self.name)

    def go_to_origin(self, wait=False) -> None:
        """Move the axis to the origin."""
        self.position_mm = 0.0
        if wait:
            self.await_movement()

    # Other Kinematic properties and methods __________________________________________________________________________

    @property
    def speed_mm_s(self) -> float:
        return self._tigerbox.get_axis_speed(self.name)

    @speed_mm_s.setter
    def speed_mm_s(self, value: float) -> None:
        self._tigerbox.set_axis_speed(axis_name=self.name, speed_mm_s=value)

    @property
    def acceleration_ms(self) -> float:
        return self._tigerbox.get_axis_acceleration(axis_name=self.name)

    @acceleration_ms.setter
    def acceleration_ms(self, value: float) -> None:
        self._tigerbox.set_axis_acceleration(axis_name=self.name, acceleration_ms=value)

    def set_backlash_mm(self, value: float) -> None:
        self._tigerbox.set_axis_backlash(axis_name=self.name, backlash_mm=value)

    # Input methods _____________________________________________________________________________________________

    def set_joystick_polarity(self, polarity: Literal[1, -1]) -> None:
        self._tigerbox.set_axis_joystick_polarity(self.name, polarity)

    def enable_joystick(self) -> None:
        self._tigerbox.enable_axis_joystick_input(self.name)

    def disable_joystick(self) -> None:
        self._tigerbox.disable_axis_joystick_input(self.name)

    # Convenience methods ____________________________________________________________________________________________

    def zero_at_center(self) -> None:
        """Move the axis to the center of the travel range."""
        self.position_mm = (self.lower_limit_mm + self.upper_limit_mm) / 2
        self.await_movement()
        self.zero_in_place()

    def zero_at_upper_limit(self) -> None:
        """Move the axis to the upper limit of the travel range."""
        self.position_mm = self.upper_limit_mm
        self.await_movement()
        self.zero_in_place()

    def zero_at_lower_limit(self) -> None:
        """Move the axis to the lower limit of the travel range."""
        self.position_mm = self.lower_limit_mm
        self.await_movement()
        self.zero_in_place()

import logging
from typing import Dict, List, Optional

from voxel.devices.controller.tiger_controller import TigerController
from voxel.devices.stage.base import BaseStage


class TigerStage(BaseStage):
    """
    Stage class for handling ASI stage devices.
    """

    def __init__(
        self,
        hardware_axis: str,
        instrument_axis: str,
        tigerbox: TigerController = None,
        port: Optional[str] = None,
        log_level: str = "INFO",
    ) -> None:
        """
        Initialize the Stage object.

        :param hardware_axis: Hardware axis
        :type hardware_axis: str
        :param instrument_axis: Instrument axis
        :type instrument_axis: str
        :param tigerbox: TigerController object, defaults to None
        :type tigerbox: Optional[TigerController], optional
        :param port: COM port for the controller, defaults to None
        :type port: Optional[str], optional
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

        # set parameter values
        # (!!) these are hardcoded here and cannot
        # be queried from the tigerbox
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

    def _instrument_to_hardware_axis_list(self, *axes: str) -> List[str]:
        """
        Convert instrument axes to hardware axes list.

        :param axes: Instrument axes
        :type axes: str
        :return: Hardware axes list
        :rtype: List[str]
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
        self.tigerbox.move_relative_mm(axis=self.hardware_axis, position=position, wait=wait)

    def move_absolute_mm(self, position: float, wait: bool = True) -> None:
        """
        Move the stage to an absolute position.

        :param position: Position to move to in millimeters
        :type position: float
        :param wait: Whether to wait for the move to complete, defaults to True
        :type wait: bool, optional
        """
        self.tigerbox.move_absolute_mm(axis=self.hardware_axis, position=position, wait=wait)

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
        self.tigerbox.setup_stage_scan(
            fast_axis=self.hardware_axis,
            fast_axis_start_position=fast_axis_start_position,
            slow_axis_start_position=slow_axis_start_position,
            slow_axis_stop_position=slow_axis_stop_position,
            frame_count=frame_count,
            frame_interval_um=frame_interval_um,
            strip_count=strip_count,
            pattern=pattern,
            retrace_speed_percent=retrace_speed_percent,
        )

    def setup_step_shoot_scan(self, step_size_um: float) -> None:
        """
        Setup a step shoot scan.

        :param step_size_um: Step size in micrometers
        :type step_size_um: float
        """
        self.tigerbox.setup_step_shoot_scan(axis=self.hardware_axis, step_size_um=step_size_um)

    def start(self) -> None:
        """
        Start the stage.
        """
        self.tigerbox.start()

    def close(self) -> None:
        """
        Close the stage.
        """
        self.tigerbox.close()

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
        self.tigerbox.move_absolute_mm(axis=self.hardware_axis, position=value, wait=False)

    @property
    def limits_mm(self) -> List[float]:
        """
        Get the limits of the stage in millimeters.

        :return: Limits in millimeters
        :rtype: List[float]
        """
        limits = self.tigerbox.get_limits_mm(axis=self.hardware_axis)
        lower_limit = self._hardware_to_instrument(limits[0])
        upper_limit = self._hardware_to_instrument(limits[1])
        sorted_limits = sorted([list(lower_limit.values())[0], list(upper_limit.values())[0]])
        return sorted_limits

    @property
    def backlash_mm(self) -> Dict[str, float]:
        """
        Get the backlash of the stage in millimeters.

        :return: Backlash in millimeters
        :rtype: Dict[str, float]
        """
        backlash = self.tigerbox.get_backlash_mm(axis=self.hardware_axis)
        return self._hardware_to_instrument(backlash)

    @backlash_mm.setter
    def backlash_mm(self, backlash: float) -> None:
        """
        Set the backlash of the stage in millimeters.

        :param backlash: Backlash in millimeters
        :type backlash: float
        """
        self.tigerbox.set_backlash_mm(axis=self.hardware_axis, backlash=backlash)

    @property
    def speed_mm_s(self) -> Dict[str, float]:
        """
        Get the speed of the stage in millimeters per second.

        :return: Speed in millimeters per second
        :rtype: Dict[str, float]
        """
        speed = self.tigerbox.get_speed_mm_s(self.hardware_axis)
        return self._hardware_to_instrument(speed)

    @speed_mm_s.setter
    def speed_mm_s(self, speed: float) -> None:
        """
        Set the speed of the stage in millimeters per second.

        :param speed: Speed in millimeters per second
        :type speed: float
        """
        self.tigerbox.set_speed_mm_s(axis=self.hardware_axis, speed=speed)

    @property
    def acceleration_ms(self) -> Dict[str, float]:
        """
        Get the acceleration of the stage in millimeters per second squared.

        :return: Acceleration in millimeters per second squared
        :rtype: Dict[str, float]
        """
        acceleration = self.tigerbox.get_acceleration_ms(axis=self.hardware_axis)
        return self._hardware_to_instrument(acceleration)

    @acceleration_ms.setter
    def acceleration_ms(self, acceleration: float) -> None:
        """
        Set the acceleration of the stage in millimeters per second squared.

        :param acceleration: Acceleration in millimeters per second squared
        :type acceleration: float
        """
        self.tigerbox.set_acceleration_ms(axis=self.hardware_axis, acceleration=acceleration)

    @property
    def mode(self) -> str:
        """
        Get the mode of the stage.

        :return: Mode of the stage
        :rtype: str
        """
        self.tigerbox.get_mode(axis=self.hardware_axis)

    @mode.setter
    def mode(self, mode: str) -> None:
        """
        Set the mode of the stage.

        :param mode: Mode of the stage
        :type mode: str
        :raises ValueError: If mode is not valid
        """
        self.tigerbox.set_mode(axis=self.hardware_axis, mode=mode)

    def halt(self) -> None:
        """
        Halt the stage.
        """
        self.tigerbox.halt_axis(axis=self.hardware_axis)

    def is_axis_moving(self) -> bool:
        """
        Check if the axis is moving.

        :return: True if the axis is moving, False otherwise
        :rtype: bool
        """
        return self.tigerbox.is_moving(axis=self.hardware_axis)

    def zero_in_place(self) -> None:
        """
        Zero the stage in place.
        """
        # We must populate the axes explicitly since the tigerbox is shared
        # between camera stage and sample stage.
        self.tigerbox.zero_axis(axis=self.hardware_axis)

    def log_metadata(self) -> None:
        """
        Log metadata.
        """
        self.tigerbox.log_metadata(axis=self.hardware_axis)

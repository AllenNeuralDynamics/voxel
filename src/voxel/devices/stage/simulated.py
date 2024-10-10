import logging
import time
import random
from voxel.devices.stage.base import BaseStage
from voxel.devices.joystick.base import BaseJoystick
from voxel.devices.joystick.axes_mapping import AxesMapping
from voxel.devices.utils.singleton import Singleton

JOYSTICK_AXES = {
    "joystick_x": 0,
    "joystick_y": 1,
    "wheel_z": 2,
    "wheel_f": 3,
    "None": 4
}

POLARITY = {
    "inverted": 0,
    "default": 1,
}

# singleton wrapper around AxesMapping
# TODO: this seems like a roundabout way of getting this to work...
class AxesMappingSingleton(AxesMapping, metaclass=Singleton):
    def __init__(self):
        super(AxesMappingSingleton, self).__init__()


class Stage(BaseStage):

    def __init__(self, hardware_axis: str, instrument_axis: str):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._hardware_axis = hardware_axis.upper()
        self._instrument_axis = instrument_axis.lower()
        self.axes_mapping = AxesMappingSingleton()
        self.axes_mapping.axis_map[instrument_axis] = hardware_axis
        # TODO change this, but self.id for consistency in lookup
        self.id = self.instrument_axis
        self._position_mm = 0
        self._speed = 1.0
        self._limits = [-10000, 10000]

    def move_relative_mm(self, position: float, wait: bool = False):
        w_text = "" if wait else "NOT "
        self.log.info(f"relative move by: {self.hardware_axis}={position} mm and {w_text}waiting.")
        move_time_s = position / self._speed
        self.move_end_time_s = time.time() + move_time_s
        self._position_mm += position
        if wait:
            while time.time() < self.move_end_time_s:
                time.sleep(0.01)

    def move_absolute_mm(self, position: float, wait: bool = False):
        w_text = "" if wait else "NOT "
        self.log.info(f"absolute move to: {self.hardware_axis}={position} mm and {w_text}waiting.")
        move_time_s = abs(self._position_mm - position) / self._speed
        self.move_end_time_s = time.time() + move_time_s
        self._position_mm = position
        if wait:
            while time.time() < self.move_end_time_s:
                time.sleep(0.01)

    def setup_stage_scan(self, fast_axis_start_position: float,
                         slow_axis_start_position: float,
                         slow_axis_stop_position: float,
                         frame_count: int, frame_interval_um: float,
                         strip_count: int, pattern: str,
                         retrace_speed_percent: int):

        self._position_mm = fast_axis_start_position

    def halts(self):
        """Simulates stopping stage"""
        pass

    @property
    def limits_mm(self):
        """ Get the travel limits for the specified axes.

        :return: a dict of 2-value lists, where the first element is the lower
            travel limit and the second element is the upper travel limit.
        """

        return self._limits

    @property
    def position_mm(self):
        return self._position_mm

    @position_mm.setter
    def position_mm(self, value):
        self._position_mm = value

    @property
    def speed_mm_s(self):
        return self._speed

    @speed_mm_s.setter
    def speed_mm_s(self, speed_mm_s: float):
        self._speed = speed_mm_s

    @property
    def hardware_axis(self):
        return self._hardware_axis

    @property
    def instrument_axis(self, ):
        return self._instrument_axis

    def is_axis_moving(self):
        if time.time() < self.move_end_time_s:
            return True
        else:
            return False

    def zero_in_place(self):
        self._position_mm = 0

    def close(self):
        pass


class Joystick(BaseJoystick):

    def __init__(self, joystick_mapping: dict = None):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._joystick_mapping = joystick_mapping if joystick_mapping is not None else \
            {"joystick_x": {"instrument_axis": "x", "polarity": "default"},
             "joystick_y": {"instrument_axis": "y", "polarity": "default"},
             "wheel_z": {"instrument_axis": "z", "polarity": "default"},
             "wheel_f": {"instrument_axis": "w", "polarity": "default"},
             }
        self._stage_axes = ['x', 'y', 'z', 'w', 'm']
        self.axes_mapping = AxesMappingSingleton().axis_map
        for axis in self._stage_axes:
            if axis not in self.axes_mapping.keys():
                self.axes_mapping[axis] = axis
        # grab the instrument to hardware axis mapping for the joystick device
        for joystick_id, joystick_dict in self.joystick_mapping.items():
            # check that the joystick ids are valid
            if joystick_id not in JOYSTICK_AXES.keys():
                raise ValueError(f"{joystick_id} must be in {JOYSTICK_AXES.keys()}")
            # check that ther polarities are valid
            joystick_polarity = joystick_dict["polarity"]
            if joystick_polarity not in POLARITY.keys():
                raise ValueError(f"{joystick_polarity} must be in {POLARITY.keys()}")
            instrument_axis = joystick_dict["instrument_axis"]
            hardware_axis = self.axes_mapping[instrument_axis]
            # check that the axes are valid
            if hardware_axis not in self._stage_axes:
                raise ValueError(
                    f"instrument axis = {instrument_axis}, hardware_axis = {hardware_axis} is not a valid axis.")

    @property
    def stage_axes(self):
        return self._stage_axes

    @property
    def joystick_mapping(self):
        return self._joystick_mapping

    @joystick_mapping.setter
    def joystick_mapping(self, joystick_mapping):
        for joystick_id, joystick_dict in joystick_mapping.items():
            # check that the joystick ids are valid
            if joystick_id not in JOYSTICK_AXES.keys():
                raise ValueError(f"{joystick_id} must be in {JOYSTICK_AXES.keys()}")
            # check that ther polarities are valid
            joystick_polarity = joystick_dict["polarity"]
            if joystick_polarity not in POLARITY.keys():
                raise ValueError(f"{joystick_polarity} must be in {POLARITY.keys()}")
            instrument_axis = joystick_dict["instrument_axis"]
            hardware_axis = self.axes_mapping[instrument_axis]
            # check that the axes are valid
            if hardware_axis not in self._stage_axes:
                raise ValueError(
                    f"instrument axis = {instrument_axis}, hardware_axis = {hardware_axis} is not a valid axis.")

        self._joystick_mapping = joystick_mapping

    def close(self):
        pass

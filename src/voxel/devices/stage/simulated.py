import logging
import time
from voxel.devices.stage.base import BaseStage


class Stage(BaseStage):

    def __init__(self, hardware_axis: str, instrument_axis: str):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self._hardware_axis = hardware_axis.upper()
        self._instrument_axis = instrument_axis.lower()
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
    ):

        self._position_mm = fast_axis_start_position

    def halts(self):
        """Simulates stopping stage"""
        pass

    @property
    def limits_mm(self):
        """Get the travel limits for the specified axes.

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
    def instrument_axis(
        self,
    ):
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

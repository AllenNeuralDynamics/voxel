import logging

from tigerasi.device_codes import *
from tigerasi.tiger_controller import TigerController

from voxel.devices.joystick.base import BaseJoystick

JOYSTICK_AXES = {
    "joystick_x": JoystickInput.JOYSTICK_X,
    "joystick_y": JoystickInput.JOYSTICK_Y,
    "wheel_z": JoystickInput.Z_WHEEL,
    "wheel_f": JoystickInput.F_WHEEL,
    "None": JoystickInput.NONE,
}

POLARITIES = {
    "inverted": JoystickPolarity.INVERTED,
    "default": JoystickPolarity.DEFAULT,
}

INSTRUMENT_AXES = list()

class Joystick(BaseJoystick):

    def __init__(self, tigerbox: TigerController, axis_mapping: dict, joystick_mapping: dict = None):
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

        self.tigerbox = tigerbox
        self._joystick_mapping = (
            joystick_mapping
            if joystick_mapping is not None
            else {
                "joystick_x": {"instrument_axis": "x", "polarity": "default"},
                "joystick_y": {"instrument_axis": "y", "polarity": "default"},
                "wheel_z": {"instrument_axis": "z", "polarity": "default"},
                "wheel_f": {"instrument_axis": "w", "polarity": "default"},
            }
        )
        self.axis_mapping = axis_mapping
        for key, value in self.axis_mapping.items():
            INSTRUMENT_AXES.append(key)
        self._stage_axes = {
            v: k for k, v in self.axis_mapping.items() if k.upper() in self.tigerbox.axes and v.upper() in self.tigerbox.axes
        }
        for axis in self.tigerbox.axes:
            if axis.lower() not in self._stage_axes.keys():
                self._stage_axes[axis.lower()] = axis.lower()
                self.axis_mapping[axis.lower()] = axis.lower()
        # grab the instrument to hardware axis mapping for the joystick device
        for joystick_id, joystick_dict in self.joystick_mapping.items():
            # check that the joystick ids are valid
            if joystick_id not in JOYSTICK_AXES.keys():
                raise ValueError(f"{joystick_id} must be in {JOYSTICK_AXES.keys()}")
            # check that ther polarities are valid
            joystick_polarity = joystick_dict["polarity"]
            if joystick_polarity not in POLARITIES.keys():
                raise ValueError(f"{joystick_polarity} must be in {POLARITIES.keys()}")
            instrument_axis = joystick_dict["instrument_axis"]
            hardware_axis = self.axis_mapping[instrument_axis]
            # check that the axes are valid
            if hardware_axis not in self._stage_axes.keys():
                raise ValueError(
                    f"instrument axis = {instrument_axis}, hardware_axis = {hardware_axis} is not a valid axis."
                )

    # @property
    # def stage_axes(self):
    #     return self._stage_axes

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
            if joystick_polarity not in POLARITIES.keys():
                raise ValueError(f"{joystick_polarity} must be in {POLARITIES.keys()}")

            instrument_axis = joystick_dict["instrument_axis"]
            hardware_axis = self.axis_mapping[instrument_axis]
            # check that the axes are valid
            if hardware_axis not in self._stage_axes:
                raise ValueError(
                    f"instrument axis = {instrument_axis}, hardware_axis = {hardware_axis} is not a valid axis."
                )
        self._joystick_mapping = joystick_mapping

import logging

from tigerasi.device_codes import *
from tigerasi.tiger_controller import TigerController

from voxel.devices.tunable_lens.base import BaseTunableLens
from voxel.devices.utils.singleton import Singleton

# constants for Tiger ASI hardware

MODES = {
    "external": TunableLensControlMode.EXTERNAL_INPUT_NO_TEMP_COMPENSATION,
    "internal": TunableLensControlMode.TG1000_INPUT_NO_TEMP_COMPENSATION,
}


# singleton wrapper around TigerController
class TigerControllerSingleton(TigerController, metaclass=Singleton):
    def __init__(self, com_port):
        super(TigerControllerSingleton, self).__init__(com_port)


class TunableLens(BaseTunableLens):

    def __init__(self, port: str, hardware_axis: str):
        """Connect to hardware.

        :param tigerbox: TigerController instance.
        :param hardware_axis: stage hardware axis.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.tigerbox = TigerControllerSingleton(com_port=port)
        self.hardware_axis = hardware_axis.upper()
        # TODO change this, but self.id for consistency in lookup
        self.id = self.hardware_axis

    @property
    def mode(self):
        """Get the tiger axis control mode."""
        mode = self.tigerbox.get_axis_control_mode(self.hardware_axis)
        converted_mode = next(key for key, enum in MODES.items() if enum.value == mode)
        return converted_mode

    @mode.setter
    def mode(self, mode: str):
        """Set the tiger axis control mode."""

        valid = list(MODES.keys())
        if mode not in valid:
            raise ValueError("mode must be one of %r." % valid)

        self.tigerbox.set_axis_control_mode(**{self.hardware_axis: MODES[mode]})

    @property
    def signal_temperature_c(self):
        """Get the temperature in deg C."""
        state = {}
        state["Temperature [C]"] = self.tigerbox.get_etl_temp(self.hardware_axis)
        return state

    def log_metadata(self):
        self.log.info("tiger hardware axis parameters")
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f"{build_config}")
        axis_settings = self.tigerbox.get_info(self.hardware_axis)
        self.log.info("{'instrument axis': 'hardware axis'} " f"{self.sample_to_tiger_axis_map}.")
        for setting in axis_settings:
            self.log.info(f"{self.hardware_axis} axis, {setting}, {axis_settings[setting]}")

    def close(self):
        self.tigerbox.ser.close()

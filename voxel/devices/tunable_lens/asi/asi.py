from tigerasi.device_codes import *
from tigerasi.tiger_controller import TigerController

from voxel.devices.tunable_lens.base import BaseTunableLens

# constants for Tiger ASI hardware

MODES = {
    "external": TunableLensControlMode.EXTERNAL_INPUT_NO_TEMP_COMPENSATION,
    "internal": TunableLensControlMode.TG1000_INPUT_NO_TEMP_COMPENSATION,
}


class ASITunableLens(BaseTunableLens):

    def __init__(self, id: str,  tigerbox: TigerController,  hardware_axis: str):
        """Connect to ASI tunable lens.
        :param id: unique voxel id for this device.
        :param tigerbox: TigerController instance.
        :param hardware_axis: stage hardware axis.
        :type id: st
        :type tigerbox: TigerController
        :type hardware_axis: str
        """
        super().__init__(id)
        self.tigerbox = tigerbox
        self.hardware_axis = hardware_axis.upper()
        # TODO change this, but self.axis for consistency in lookup
        self.axis = self.hardware_axis

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
    def temperature_c(self):
        """Get the temperature in deg C."""
        return self.tigerbox.get_etl_temp(self.hardware_axis)

    def log_metadata(self):
        self.log.info('tiger hardware axis parameters')
        build_config = self.tigerbox.get_build_config()
        self.log.debug(f'{build_config}')
        axis_settings = self.tigerbox.get_info(self.hardware_axis)
        self.log.info(f'{self.hardware_axis} axis settings')
        for setting in axis_settings:
            self.log.info(f'{self.hardware_axis} axis, {setting}, {axis_settings[setting]}')

    def close(self):
        self.tigerbox.ser.close()

import logging

import optoICC
from optoKummenberg.tools.definitions import UnitType

from voxel.devices.tunable_lens.base import BaseTunableLens

# input constants for Optotune ICC-4C controller
# CURRENT   = 0
# OF        = 1
# XY     = 2
# FP     = 3
# UNITLESS = 4
# UNDEFINED = 5

LUT_MODES = {
    "current": UnitType.CURRENT,
    "of": UnitType.OF,
    "xy": UnitType.XY,
    "focal power": UnitType.FP,
    "unitless": UnitType.UNITLESS,
    "undefined": UnitType.UNDEFINED,
}

UNITS = {
    UnitType.CURRENT: "mA",
    UnitType.OF: "-",
    UnitType.XY: "-",
    UnitType.FP: "diopter",
    UnitType.UNITLESS: "-",
    UnitType.UNDEFINED: "-",
}

MODES = ["internal", "external"]  # static input mode  # analog input mode


class TunableLens(BaseTunableLens):
    def __init__(self, port: str, channel: int):
        """Connect to hardware."""
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.icc4c = optoICC.connect(port=port)
        self.icc4c.reset(force=True)
        self.icc4c.go_pro()
        self._channel = channel
        self.tunable_lens = self.icc4c.channel[self.channel]
        # start lens in analog mode
        self._mode = "external"
        self.tunable_lens.Analog.SetAsInput() # default to analog input mode
        self.tunable_lens.Analog.SetLUTtype(LUT_MODES["current"]) # default to current mode

    @property
    def channel(self):
        """Get the tunable lens channel number."""
        return self._channel

    @property
    def mode(self):
        """Get the tunable lens control mode."""
        return self._mode

    @mode.setter
    def mode(self, mode: str):
        """Set the tunable lens control mode."""
        self._mode = mode
        if mode == "external":
            self.tunable_lens.Analog.SetAsInput()
        elif mode == "internal":
            self.tunable_lens.StaticInput.SetAsInput()
        else:
            raise ValueError(f"{mode} must be {MODES}")

    @property
    def temperature_c(self):
        """Get the tunable lens temperature in deg C."""
        temperature = self.tunable_lens.TemperatureManager.GetDeviceTemperature()
        return temperature

    @property
    def lut_voltages(self):
        """Get the tunable lens lookup table voltages"""
        values_volts = self.tunable_lens.Analog.GetLUTvoltages()
        return values_volts

    @lut_voltages.setter
    def lut_voltages(self, values_volts: list):
        """Set the tunable lens lookup table voltages"""
        self.log.info(f'setting voltages lut to {values_volts} volts')
        self.tunable_lens.Analog.SetLUTvoltages(values_volts)

    @property
    def lut_values(self):
        """Get the tunable lens lookup table values"""
        values_mA = self.tunable_lens.Analog.GetLUTvalues()
        return values_mA

    @lut_values.setter
    def lut_values(self, values: list):
        """Set the tunable lens lookup table values"""
        unit = UNITS[self.tunable_lens.Analog.GetLUTtype()]
        self.log.info(f'setting current lut to {values} {unit}')
        self.tunable_lens.Analog.SetLUTvalues(values)

    @property
    def lut_mode(self):
        """Get the tunable lens lookup table type"""
        lut_mode = self.tunable_lens.Analog.GetLUTtype()
        return next(key for key, value in LUT_MODES.items() if value == lut_mode)

    @lut_mode.setter
    def lut_mode(self, lut_mode: list):
        """Set the tunable lens lookup table type"""
        self.log.info(f'setting lut mode to {lut_mode}')
        self.tunable_lens.Analog.SetLUTtype(LUT_MODES[lut_mode])
 
    # def close(self):
    #     """Close the tunable lens."""
    #     self.icc4c.disconnect()

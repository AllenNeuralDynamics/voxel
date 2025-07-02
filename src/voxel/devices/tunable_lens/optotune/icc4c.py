import logging
from typing import List

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


class ICC4CTunableLens(BaseTunableLens):
    """
    TunableLens class for handling Optotune ICC-4C tunable lens devices.
    """

    def __init__(self, port: str, channel: int) -> None:
        """
        Initialize the TunableLens object.

        :param port: COM port for the controller
        :type port: str
        :param channel: Channel number
        :type channel: int
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.icc4c = optoICC.connect(port=port)
        self.icc4c.reset(force=True)
        self.icc4c.go_pro()
        self._channel = channel
        self.tunable_lens = self.icc4c.channel[self.channel]
        # start lens in analog mode
        self._mode = "external"
        self.tunable_lens.Analog.SetAsInput()  # default to analog input mode
        self.tunable_lens.Analog.SetLUTtype(LUT_MODES["current"])  # default to current mode

    @property
    def channel(self) -> int:
        """
        Get the channel number.

        :return: Channel number
        :rtype: int
        """
        return self._channel

    @property
    def mode(self) -> str:
        """
        Get the mode of the tunable lens.

        :return: Mode of the tunable lens
        :rtype: str
        """
        return self._mode

    @mode.setter
    def mode(self, mode: str) -> None:
        """
        Set the mode of the tunable lens.

        :param mode: Mode of the tunable lens
        :type mode: str
        :raises ValueError: If the mode is not valid
        """
        self._mode = mode
        if mode == "external":
            self.tunable_lens.Analog.SetAsInput()
        elif mode == "internal":
            self.tunable_lens.StaticInput.SetAsInput()
        else:
            raise ValueError(f"{mode} must be {MODES}")

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the tunable lens in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        temperature = self.tunable_lens.TemperatureManager.GetDeviceTemperature()
        return temperature

    @property
    def lut_voltages(self) -> List[float]:
        """
        Get the LUT voltages.

        :return: LUT voltages
        :rtype: list
        """
        values_volts = self.tunable_lens.Analog.GetLUTvoltages()
        return values_volts

    @lut_voltages.setter
    def lut_voltages(self, values_volts: List[float]) -> None:
        """
        Set the LUT voltages.

        :param values_volts: LUT voltages
        :type values_volts: list
        """
        self.log.info(f"setting voltages lut to {values_volts} volts")
        self.tunable_lens.Analog.SetLUTvoltages(values_volts)

    @property
    def lut_values(self) -> List[float]:
        """
        Get the LUT values.

        :return: LUT values
        :rtype: list
        """
        values_mA = self.tunable_lens.Analog.GetLUTvalues()
        return values_mA

    @lut_values.setter
    def lut_values(self, values: List[float]) -> None:
        """
        Set the LUT values.

        :param values: LUT values
        :type values: list
        """
        unit = UNITS[self.tunable_lens.Analog.GetLUTtype()]
        self.log.info(f"setting current lut to {values} {unit}")
        self.tunable_lens.Analog.SetLUTvalues(values)

    @property
    def lut_mode(self) -> str:
        """
        Get the LUT mode.

        :return: LUT mode
        :rtype: str
        """
        lut_mode = self.tunable_lens.Analog.GetLUTtype()
        return next(key for key, value in LUT_MODES.items() if value == lut_mode)

    @lut_mode.setter
    def lut_mode(self, lut_mode: str) -> None:
        """
        Set the LUT mode.

        :param lut_mode: LUT mode
        :type lut_mode: str
        """
        self.log.info(f"setting lut mode to {lut_mode}")
        self.tunable_lens.Analog.SetLUTtype(LUT_MODES[lut_mode])

    def close(self) -> None:
        """
        Close the tunable lens device.
        """
        self.log.info("closing tunable lens.")
        self.icc4c.disconnect()

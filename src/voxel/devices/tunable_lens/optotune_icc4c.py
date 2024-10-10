import logging
import optoICC
from optoKummenberg.tools.definitions import UnitType
from voxel.devices.tunable_lens.base import BaseTunableLens

# constants for Optotune ICC-4C controller
# CURRENT   = 0
# OF        = 1
# XY     = 2
# FP     = 3
# UNITLESS = 4
# UNDEFINED = 5

MODES = {"internal": UnitType.FP,
         "external": UnitType.CURRENT}

class TunableLens(BaseTunableLens):

    def __init__(self, port: str, channel: int):
        """Connect to hardware.

        :param tigerbox: TigerController instance.
        :param hardware_axis: stage hardware axis.
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.icc4c = optoICC.connect(port=port)
        self.icc4c.reset(force=True)
        self.icc4c.go_pro()
        self._channel = channel
        self.tunable_lens = self.icc4c.channel[self.channel]
        # start lens in internal mode
        self.tunable_lens.SetControlMode(UnitType.FP)
        self._mode = "internal"

    @property
    def channel(self):
        return self._channel

    @property
    def mode(self):
        """Get the tunable lens control mode."""
        mode = self.tunable_lens.GetControlMode()
        return next(key for key, value in MODES.items() if value == mode)

    @mode.setter
    def mode(self, mode: str):
        """Set the tunable lens control mode."""
        if mode not in MODES.keys():
            raise ValueError(f"{mode} must be {MODES}")
        self.tunable_lens.SetControlMode(MODES[mode])

    @property
    def signal_temperature_c(self):
        """Get the temperature in deg C."""
        state = {}
        state['Temperature [C]'] = self.tunable_lens.TemperatureManager.GetDeviceTemperature()
        return state

    def close(self):
        self.icc4c.close()
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

MODES = {"internal": UnitType.FP, "external": UnitType.CURRENT}


class OptotuneICC4CTunableLens(BaseTunableLens):

    def __init__(self, id: str, port: str, channel: int):
        """Connect to OptotuneI ICC-4C Tunable Lens.
        :param id: unique voxel id for this device.
        :param port: serial port for the ICC-4-C controller.
        :param channel: channel number for the tunable lens.
        :type id: str
        :type port: str
        :type channel: int
        """
        super().__init__(id)
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
    def temperature_c(self):
        """Get the temperature in deg C."""
        return {
            "Temperature [C]": self.tunable_lens.TemperatureManager.GetDeviceTemperature()
        }

    def log_metadata(self):
        return {
            "id": self.id,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
        }

    def close(self):
        self.icc4c.close()


# Example usage:
if __name__ == "__main__":
    etl = OptotuneICC4CTunableLens(id="optotune", port='COM7', channel=0)
    print(etl.temperature_c)
    print(etl.mode)
    etl.mode = 'internal'
    print(etl.mode)
    etl.mode = 'external'
    print(etl.mode)
    print(etl.log_metadata())
    etl.close()

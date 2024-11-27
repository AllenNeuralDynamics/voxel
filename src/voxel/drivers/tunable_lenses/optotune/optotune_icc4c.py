import optoICC
from optoKummenberg.tools.definitions import UnitType


from voxel.instrument.devices.tunable_lens import VoxelTunableLens, TunableLensControlMode

# constants for Optotune ICC-4C controller
# CURRENT   = 0
# OF        = 1
# XY     = 2
# FP     = 3
# UNITLESS = 4
# UNDEFINED = 5

MODES = {TunableLensControlMode.INTERNAL: UnitType.FP, TunableLensControlMode.EXTERNAL: UnitType.CURRENT}


class OptotuneICC4CTunableLens(VoxelTunableLens):
    def __init__(self, name: str, port: str, channel: int):
        """Connect to OptotuneI ICC-4C Tunable Lens.
        :param name: unique voxel name for this device.
        :param port: serial port for the ICC-4-C controller.
        :param channel: channel number for the tunable lens.
        :type name: str
        :type port: str
        :type channel: int
        """
        super().__init__(name)
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
    def mode(self) -> TunableLensControlMode:
        """Get the tunable lens control mode."""
        mode = self.tunable_lens.GetControlMode()
        return next(key for key, value in MODES.items() if value == mode)

    @mode.setter
    def mode(self, mode: TunableLensControlMode):
        """Set the tunable lens control mode."""
        self.tunable_lens.SetControlMode(MODES[mode])

    @property
    def temperature_c(self):
        """Get the temperature in deg C."""
        return {"Temperature [C]": self.tunable_lens.TemperatureManager.GetDeviceTemperature()}

    def log_metadata(self):
        return {
            "name": self.name,
            "mode": self.mode,
            "temperature_c": self.temperature_c,
        }

    def close(self):
        self.icc4c.close()

from obis_laser import ObisLS
from serial import Serial

from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

from .obis_lx import obis_modulation_getter, obis_modulation_setter

MODULATION_MODES = {'off': 'CWP', 'analog': 'ANALOG', 'digital': 'DIGITAL', 'mixed': 'MIXED'}


class ObisLSLaser(VoxelLaser):
    def __init__(self, name: str, wavelength: int, port: Serial | str, prefix: str | None = None) -> None:
        """Communicate with specific LS laser.

        :param port: comm port for lasers.
        :param wavelength: wavelength of laser
        :param prefix: prefix specic to laser.
        """
        super().__init__(name=name, wavelength=wavelength)
        self.prefix = prefix
        self._inst = ObisLS(port, self.prefix)

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    def close(self):
        self._inst.ser.close()

    @deliminated_float(min_value=0, max_value=lambda self: self._inst.max_power)
    def power_setpoint_mw(self):
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float):
        self._inst.power_setpoint = value

    @property
    def modulation_mode(self) -> str | None:
        """Get the modulation mode of the laser.

        Can be one of two categories:
            - External Control - Analog, Digital, Mixed
            - Internal Control - off: CWP
        """
        return obis_modulation_getter(self._inst, self.log, modes=MODULATION_MODES)

    @modulation_mode.setter
    def modulation_mode(self, mode: str) -> None:
        """Set the modulation mode of the laser.

        Can be one of two categories:
            - External Control - Analog, Digital, Mixed
            - Internal Control - off: CWP

        Args:
            mode: Modulation mode as a string.

        """
        obis_modulation_setter(self._inst, mode, modes=MODULATION_MODES)

    @property
    def power_mw(self) -> float:
        return self._inst.power_setpoint

    @property
    def temperature_c(self) -> float:
        return self._inst.temperature

    @property
    def status(self):
        return self._inst.get_system_status()

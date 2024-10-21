from obis_laser import ObisLS
from serial import Serial

from voxel.core.utils.descriptors.deliminated_property import deliminated_property
from .obis_lx import obis_modulation_getter, obis_modulation_setter
from voxel.core.instrument.device.laser import VoxelLaser

MODULATION_MODES = {"off": "CWP", "analog": "ANALOG", "digital": "DIGITAL", "mixed": "MIXED"}


class ObisLSLaser(VoxelLaser):
    def __init__(self, name: str, wavelength: int, port: Serial | str, prefix: str = None):
        """
        Communicate with specific LS laser.

        :param port: comm port for lasers.
        :param wavelength: wavelength of laser
        :param prefix: prefix specic to laser.
        """
        super().__init__(name)
        self.prefix = prefix
        self._wavelength = wavelength
        self._inst = ObisLS(port, self.prefix)

    @property
    def wavelength(self) -> int:
        return self._wavelength

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    def close(self):
        self._inst.close()

    @deliminated_property(minimum=0, maximum=lambda self: self._inst.max_power)
    def power_setpoint_mw(self):
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float | int):
        self._inst.power_setpoint = value

    @property
    def modulation_mode(self):
        """
        The modulation mode of the laser can be one of two categories:

        External Control - Analog, Digital, Mixed

        Internal Control - off: CWP
        """
        return obis_modulation_getter(self._inst, self.log, modes=MODULATION_MODES)

    @modulation_mode.setter
    def modulation_mode(self, mode: str) -> None:
        """
        The modulation mode of the laser can be one of two categories:   \n
        External Control - Analog, Digital, Mixed \n
        Internal Control - off: CWP \n
        :param mode: str
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

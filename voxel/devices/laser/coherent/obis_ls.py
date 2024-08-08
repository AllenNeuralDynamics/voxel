from obis_laser import ObisLS, OperationalQuery, OperationalCmd
from ..base import BaseLaser
from .obis_lx import obis_modulation_getter, obis_modulation_setter
from serial import Serial
from voxel.descriptors.deliminated_property import DeliminatedProperty

MODULATION_MODES = {
    'off': 'CWP',
    'analog': 'ANALOG',
    'digital': 'DIGITAL',
    'mixed': 'MIXED'
}


class ObisLSLaser(BaseLaser):
    def __init__(self, id: str, port: Serial | str, prefix: str = None):
        """
        Communicate with specific LS laser.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        """
        super().__init__(id)
        self.prefix = prefix
        self._inst = ObisLS(port, self.prefix)

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    def close(self):
        self._inst.close()

    @DeliminatedProperty(minimum=0, maximum=lambda self: self._inst.max_power)
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

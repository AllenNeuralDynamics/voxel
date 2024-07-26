from vortran_laser import StradusLaser as StradusVortran, BoolVal

from voxel.descriptors.deliminated_property import deliminated_property
from voxel.devices.lasers.base import BaseLaser

MODULATION_MODES = {
    'off': {'external_control': BoolVal.OFF, 'digital_modulation': BoolVal.OFF},
    'analog': {'external_control': BoolVal.ON, 'digital_modulation': BoolVal.OFF},
    'digital': {'external_control': BoolVal.OFF, 'digital_modulation': BoolVal.ON}
}


class StradusLaser(BaseLaser):

    def __init__(self, id: str, port: str):
        """
        Communicate with stradus laser.

        :param port: comm port for lasers.
        """
        super().__init__(id)
        self._inst = StradusVortran(port)

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
        if self._inst.external_control == BoolVal.ON:
            return 'analog'
        elif self._inst.digital_modulation == BoolVal.ON:
            return 'digital'
        else:
            return 'off'

    @modulation_mode.setter
    def modulation_mode(self, value: str):
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._inst, attribute, state)

    @property
    def power_mw(self) -> float:
        return self._inst.power

    @property
    def temperature_c(self) -> float:
        return self._inst.temperature

    @property
    def status(self):
        return self._inst.faults

from typing import Literal

from pyparsing import Any
from vortran_laser import BoolVal
from vortran_laser import StradusLaser as StradusVortran
from voxel.devices.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

MODULATION_MODES = {
    'off': {'external_control': BoolVal.OFF, 'digital_modulation': BoolVal.OFF},
    'analog': {'external_control': BoolVal.ON, 'digital_modulation': BoolVal.OFF},
    'digital': {'external_control': BoolVal.OFF, 'digital_modulation': BoolVal.ON},
}


class StradusLaser(VoxelLaser):
    def __init__(self, name: str, port: str, wavelength: int) -> None:
        """Communicate with stradus laser.

        :param port: comm port for lasers.
        :param wavelength: wavelength of laser
        """
        super().__init__(uid=name, wavelength=wavelength)
        self._inst = StradusVortran(port)

    def enable(self) -> None:
        self._inst.enable()

    def disable(self) -> None:
        self._inst.disable()

    def close(self) -> None:
        self._inst.ser.close()

    @deliminated_float(min_value=0, max_value=lambda self: self._inst.max_power)
    def power_setpoint_mw(self) -> float:
        return float(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        self._inst.power_setpoint = value

    @property
    def modulation_mode(self) -> Literal['off', 'analog', 'digital']:
        if self._inst.external_control == BoolVal.ON:
            return 'analog'
        if self._inst.digital_modulation == BoolVal.ON:
            return 'digital'
        return 'off'

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        if value not in MODULATION_MODES:
            raise ValueError('mode must be one of %r.' % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._inst, attribute, state)

    @property
    def power_mw(self) -> float:
        return float(self._inst.power)

    @property
    def temperature_c(self) -> float:
        return float(self._inst.temperature)

    @property
    def status(self) -> None | list[Any]:
        return self._inst.faults

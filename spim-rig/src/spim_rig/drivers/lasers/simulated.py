import random

from spim_rig.laser.base import SpimLaser

from pyrig.props import deliminated_float


class SimulatedLaser(SpimLaser):
    def __init__(self, uid: str, wavelength: int, max_power_mw: float = 1000.0) -> None:
        self._max_power_mw = max_power_mw
        self._power_setpoint_mw = 10.0
        self._is_enabled = False
        self._temperature = 20.0
        super().__init__(uid=uid, wavelength=wavelength)

    def enable(self) -> None:
        self._is_enabled = True

    def disable(self) -> None:
        self._is_enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @deliminated_float(min_value=0.0, max_value=lambda self: self._max_power_mw, step=1.0)
    def power_setpoint_mw(self) -> float:
        return self._power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        self._power_setpoint_mw = value
        self.log.info(f"Power setpoint changed to {value} mW")

    @property
    def power_mw(self) -> float:
        if not self._is_enabled:
            return 0.0
        return random.gauss(self._power_setpoint_mw, 0.1)

    @property
    def temperature_c(self) -> float:
        return self._temperature + random.gauss(0, 0.1)

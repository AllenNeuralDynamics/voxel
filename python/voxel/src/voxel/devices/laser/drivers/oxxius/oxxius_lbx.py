from typing import Any, Literal

from oxxius_laser import LBX, BoolVal
from serial import Serial
from sympy import Expr, S, solve, symbols

from voxel.devices.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

MODULATION_MODES = {
    'off': {'external_control_mode': BoolVal.OFF, 'digital_modulation': BoolVal.OFF},
    'analog': {'external_control_mode': BoolVal.ON, 'digital_modulation': BoolVal.OFF},
    'digital': {'external_control_mode': BoolVal.OFF, 'digital_modulation': BoolVal.ON},
}


class OxxiusLBXLaser(VoxelLaser):
    def __init__(self, name: str, port: Serial | str, wavelength: int, prefix: str, coefficients: dict) -> None:
        """Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param coefficients: polynomial coefficients describing
        :param wavelength: wavelength of laser
        the relationship between current percentage and power mw
        """
        super().__init__(name=name, wavelength=wavelength)
        self._prefix = prefix
        self._inst = LBX(port, self._prefix)
        self._coefficients = coefficients

    def enable(self) -> None:
        self._inst.enable()

    def disable(self) -> None:
        self._inst.disable()

    @deliminated_float(min_value=0, max_value=lambda self: self.max_power)
    def power_setpoint_mw(self) -> float:
        if self._inst.constant_current == 'ON':
            val = self._coefficients_curve().subs(symbols('x'), self._inst.current_setpoint)
            return round(float(val))  # pyright: ignore[reportArgumentType]
        return int(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        if self._inst.constant_current == 'ON':
            solutions = solve(self._coefficients_curve() - S(value))
            for sol in solutions:
                try:
                    cur = float(sol)
                except TypeError:
                    cur = float(sol.evalf())
                if round(cur) in range(101):
                    self._inst.current_setpoint = round(cur)
                    return
            self.log.error('Unable to set laser power. No current percent correlates to %smW', value)
        else:
            self._inst.power_setpoint = value

    @property
    def modulation_mode(self) -> Literal['analog', 'digital', 'off']:
        if self._inst.external_control_mode == 'ON':
            return 'analog'
        if self._inst.digital_modulation == 'ON':
            return 'digital'
        return 'off'

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        if value not in MODULATION_MODES:
            raise ValueError('mode must be one of %r.' % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._inst, attribute, state)

    def status(self) -> list[Any] | None:
        return self._inst.faults

    def close(self) -> None:
        self._inst.ser.close()

    @property
    def power_mw(self) -> float:
        return float(self._inst.power)

    @property
    def temperature_c(self) -> float:
        return float(self._inst.temperature)

    def _coefficients_curve(self) -> Expr:
        x = symbols('x')
        func: Expr = x
        for order, co in self._coefficients.items():
            func = func + S(float(co)) * x ** int(order)
        return func

    @property
    def max_power(self) -> float:
        if self._inst.constant_current == 'ON':
            val = self._coefficients_curve().subs(symbols('x'), 100)
            return int(round(float(val), 1))  # pyright: ignore[reportArgumentType] #
        return float(self._inst.max_power)

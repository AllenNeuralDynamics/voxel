from oxxius_laser import LBX, BoolVal
from serial import Serial
from sympy import Expr, solve, symbols

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser

MODULATION_MODES = {
    "off": {"external_control_mode": BoolVal.OFF, "digital_modulation": BoolVal.OFF},
    "analog": {"external_control_mode": BoolVal.ON, "digital_modulation": BoolVal.OFF},
    "digital": {"external_control_mode": BoolVal.OFF, "digital_modulation": BoolVal.ON},
}


class OxxiusLBXLaser(BaseLaser):

    def __init__(self, id: str, port: Serial or str, wavelength: int, prefix: str, coefficients: dict):
        """
        Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param coefficients: polynomial coefficients describing
        :param wavelength: wavelength of laser
        the relationship between current percentage and power mw
        """
        super().__init__(id)
        self._prefix = prefix
        self._inst = LBX(port, self._prefix)
        self._coefficients = coefficients
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        return self._wavelength

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    @property
    @DeliminatedProperty(minimum=0, maximum=lambda self: self.max_power)
    def power_setpoint_mw(self):
        if self._inst.constant_current == "ON":
            return int(round(self._coefficients_curve().subs(symbols("x"), self._inst.current_setpoint)))
        else:
            return int(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float or int):
        if self._inst.constant_current == "ON":
            solutions = solve(self._coefficients_curve() - value)  # solutions for laser value
            for sol in solutions:
                if round(sol) in range(0, 101):
                    self._inst.current_setpoint = int(round(sol))  # setpoint must be integer
                    return
            # If no value exists, alert user
            self.log.error(f"Cannot set laser to {value}mW because " f"no current percent correlates to {value} mW")
        else:
            self._inst.power_setpoint = value

    @property
    def modulation_mode(self):
        if self._inst.external_control_mode == "ON":
            return "analog"
        elif self._inst.digital_modulation == "ON":
            return "digital"
        else:
            return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str):
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._inst, attribute, state)
        self._set_max_power()

    def status(self):
        return self._inst.faults()

    def close(self):
        self._inst.close()

    @property
    def power_mw(self) -> float:
        return self._inst.power

    @property
    def temperature_c(self):
        return self._inst.temperature

    def _coefficients_curve(self) -> Expr:
        x = symbols("x")
        func: Expr = x
        for order, co in self._coefficients.items():
            func = func + float(co) * x ** int(order)
        return func

    @property
    def max_power(self):
        if self._inst.constant_current == "ON":
            return int((round(self._coefficients_curve().subs(symbols("x"), 100), 1)))
        else:
            return self._inst.max_power

    def _set_max_power(self):
        type(self.power_setpoint_mw).maximum = self.max_power

from typing import Dict, Union

from oxxius_laser.oxxius_laser import LBX, BoolVal, Cmd, OxxiusController, Query
from sympy import Expr, solve, symbols

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser

MODULATION_MODES = {
    "off": {"external_control_mode": BoolVal.OFF, "digital_modulation": BoolVal.OFF},
    "analog": {"external_control_mode": BoolVal.ON, "digital_modulation": BoolVal.OFF},
    "digital": {"external_control_mode": BoolVal.OFF, "digital_modulation": BoolVal.ON},
}


class OxxiusLBXLaser(BaseLaser):
    """
    OxxiusLBXLaser class for handling Oxxius LBX laser devices.
    """

    def __init__(
        self, id: str,
        wavelength: int,
        prefix: str,
        coefficients: Dict[str, float] = None,
        port: str = None,
        controller: OxxiusController = None,
    ) -> None:
        """_summary_

        :param id: _description_
        :type id: str
        :param wavelength: _description_
        :type wavelength: int
        :param prefix: _description_
        :type prefix: str
        :param coefficients: _description_, defaults to None
        :type coefficients: Dict[str, float], optional
        :param port: _description_, defaults to None
        :type port: str, optional
        :param controller: _description_, defaults to None
        :type controller: OxxiusController, optional
        """
        super().__init__(id)

        if controller is None and port is None:
            raise ValueError("Controller and port cannot both be none")

        self._controller = LBX(port, self._prefix) if controller is None else controller
        self._prefix = prefix
        self._coefficients = coefficients
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

    def enable(self) -> None:
        """
        Enable laser emission.
        """
        self._controller.set(self._prefix, Cmd.LaserEmission, BoolVal.ON)

    def disable(self) -> None:
        """
        Disable laser emission.
        """
        self._controller.set(self._prefix, Cmd.LaserEmission, BoolVal.OFF)

    @property
    @DeliminatedProperty(minimum=0, maximum=lambda self: self.max_power)
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint.

        :return: Power setpoint.
        :rtype: str
        """
        if self._get_constant_current() == "ON":
            return int(round(self._coefficients_curve().subs(symbols("x"), self._controller.get(self._prefix, Query.LaserPowerSetting))))
        else:
            return int(self._controller.get(self._prefix, Query.LaserPowerSetting))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: Union[float, int]) -> None:
        """
        Set the power setpoint in milliwatts.

        :param value: Power setpoint in milliwatts
        :type value: float or int
        """
        if self._get_constant_current() == "ON":
            solutions = solve(self._coefficients_curve() - value)  # solutions for laser value
            for sol in solutions:
                if round(sol) in range(0, 101):
                    if 0 > value > 100:
                        reason = "exceeds 100%" if value > self.max_power else f"is below 0%"
                        self.log.error(f"Cannot set laser to {value}ml because it {reason}")
                    else:
                        if self._get_constant_current() == BoolVal.OFF:
                            self.log.warning(
                                "Laser is in constant power mode so changing power will not change intensity"
                            )
                        self._controller.set(self._prefix, Cmd.LaserCurrent, value)
                    return
            # If no value exists, alert user
            self.log.error(f"Cannot set laser to {value}mW because no current percent correlates to {value} mW")
        else:
            if 0 > value > self.max_power:
                reason = (
                    f"exceeds maximum power output {self.max_power}mW"
                    if value > self.max_power
                    else "is below 0mW"
                )
                self.log.error(f"Cannot set laser to {value}ml because it {reason}")
            else:
                if self._get_constant_current() == BoolVal.ON:
                    self.log.warning(
                        "Laser is in constant current mode so changing power will not change intensity"
                    )
                self._controller.set(self._prefix, Cmd.LaserPower, value)

    @property
    def modulation_mode(self) -> str:
        """
        Get the modulation mode.

        :return: Modulation mode
        :rtype: str
        """
        if self._controller.external_control_mode == "ON":
            return "analog"
        elif self._controller.digital_modulation == "ON":
            return "digital"
        else:
            return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """
        Set the modulation mode.

        :param value: Modulation mode
        :type value: str
        :raises ValueError: If the modulation mode is not valid
        """
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._controller, attribute, state)
        self._set_max_power()

    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser
        :rtype: dict
        """
        return self._controller.faults()

    def close(self) -> None:
        """
        Close the laser connection.
        """
        self.disable()
        if self._controller.ser.is_open:
            self._controller.ser.close()

    @property
    def power_mw(self) -> float:
        """
        Get the current laser power.

        :return: Current laser power.
        :rtype: str
        """
        return self._controller.get(self._prefix, Query.LaserPower)

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return self._controller.temperature

    def _coefficients_curve(self) -> Expr:
        """
        Get the power-current curve as a symbolic expression.

        :return: Power-current curve
        :rtype: Expr
        """
        x = symbols("x")
        func: Expr = x
        for order, co in self._coefficients.items():
            func = func + float(co) * x ** int(order)
        return func

    @property
    def max_power(self) -> float:
        """
        Get the maximum power in milliwatts.

        :return: Maximum power in milliwatts
        :rtype: float
        """
        if self._get_constant_current() == "ON":
            return int((round(self._coefficients_curve().subs(symbols("x"), 100), 1)))
        else:
            return self._controller.get(self._prefix, Query.MaximumLaserPower)

    def _set_max_power(self) -> None:
        """
        Set the maximum power.
        """
        type(self.power_setpoint_mw).maximum = self.max_power

    def _get_constant_current(self) -> bool:
        """
        Get the constant current mode status.

        :return: Constant current mode status.
        :rtype: BoolVal
        """
        return BoolVal(self._controller.get(self._prefix, Query.LaserDriverControlMode))

    def _set_constant_current(self, value: BoolVal) -> None:
        """
        Set the constant current mode status.

        :param value: Desired constant current mode status.
        :type value: BoolVal
        """
        if value == BoolVal.OFF and self._controller.digital_modulation == BoolVal.ON:
            self.log.warning(
                f"Putting Laser {self.prefix} in constant power mode and disabling digital modulation mode"
            )
        self._controller.set(self._prefix, Cmd.LaserDriverControlMode, value)

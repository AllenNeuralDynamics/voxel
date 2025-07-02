from typing import Dict, Union

from sympy import Expr, solve, symbols

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.controller.oxxius.lxcc import BoolVal, Cmd, OxxiusController, Query
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
        self,
        id: str,
        prefix: str,
        wavelength: float,
        coefficients: Dict[str, float] = None,
        port: str = None,
        controller: OxxiusController = None,
    ) -> None:
        """
        Initialize an OxxiusLBXLaser instance.

        :param id: Laser identifier.
        :type id: str
        :param prefix: Command prefix for the laser.
        :type prefix: str
        :param wavelength: Wavelength of the laser in nanometers.
        :type wavelength: float
        :param coefficients: Coefficients for the power-current curve.
        :type coefficients: dict, optional
        :param port: Serial port name, defaults to None.
        :type port: str, optional
        :param controller: OxxiusController instance, defaults to None.
        :type controller: OxxiusController, optional
        :raises ValueError: If both controller and port are None.
        """
        super().__init__(id)

        if controller is None and port is None:
            raise ValueError("Controller and port cannot both be none")

        if controller is None:
            self._controller = OxxiusController(port=port)
        else:
            self._controller = controller
        self._prefix = prefix
        type(self).power_setpoint_mw.maximum = self.max_power
        self._wavelength = wavelength
        self._coefficients = coefficients
        # initialize laser modulation mode to off
        # note cannot change mode without first disabling laser
        self.disable()
        self._set_constant_current(BoolVal.OFF)
        self.modulation_mode = "off"

    @property
    def wavelength(self) -> float:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers.
        :rtype: float
        """
        return self._wavelength

    def enable(self) -> None:
        """
        Enable laser emission.

        :return: None
        """
        self._controller.set(Cmd.LaserEmission, BoolVal.ON, self._prefix)
        self.log.info("laser enabled")

    def disable(self) -> None:
        """
        Disable laser emission.

        :return: None
        """
        self._controller.set(Cmd.LaserEmission, BoolVal.OFF, self._prefix)
        self.log.info("laser disabled")

    @DeliminatedProperty(minimum=0, maximum=float("inf"))
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint.

        :return: Power setpoint in milliwatts.
        :rtype: float
        """
        if self._get_constant_current() == BoolVal.ON:
            return float(
                round(
                    self._coefficients_curve().subs(
                        symbols("x"), self._controller.get(Query.LaserCurrentSetting, self._prefix)
                    )
                )
            )
        else:
            return float(self._controller.get(Query.LaserPowerSetting, self._prefix))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """
        Set the power setpoint in milliwatts.

        :param value: Power setpoint in milliwatts.
        :type value: float
        :return: None
        """
        if self._get_constant_current() == BoolVal.ON:
            solutions = solve(self._coefficients_curve() - value)
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
                        self._controller.set(Cmd.LaserCurrent, int(sol), self._prefix)
                    return
            self.log.error(f"Cannot set laser to {value}mW because no current percent correlates to {value} mW")
        else:
            if 0 > value > self.max_power:
                reason = (
                    f"exceeds maximum power output {self.max_power}mW" if value > self.max_power else "is below 0mW"
                )
                self.log.error(f"Cannot set laser to {value}ml because it {reason}")
            else:
                if self._get_constant_current() == BoolVal.ON:
                    self.log.warning("Laser is in constant current mode so changing power will not change intensity")
                self._controller.set(Cmd.LaserPower, value, self._prefix)
        self.log.info(f"power set to {value} mW")

    @property
    def modulation_mode(self) -> str:
        """
        Get the modulation mode.

        :return: Modulation mode ('off', 'analog', or 'digital').
        :rtype: str
        """
        external_control_mode = BoolVal(self._controller.get(Query.ExternalPowerControl, self._prefix))
        digital_modulation = BoolVal(self._controller.get(Query.DigitalModulation, self._prefix))
        if external_control_mode == BoolVal.ON:
            return "analog"
        elif digital_modulation == BoolVal.ON:
            return "digital"
        else:
            return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """
        Set the modulation mode.

        :param value: Modulation mode ('off', 'analog', or 'digital').
        :type value: str
        :raises ValueError: If the modulation mode is not valid.
        :return: None
        """
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        states = MODULATION_MODES[value]
        # needs to be set first otherwise digital ON is rejected
        if states["digital_modulation"] == BoolVal.ON:
            self._set_constant_current(BoolVal.ON)
        else:
            self._set_constant_current(BoolVal.OFF)
        self._controller.set(Cmd.DigitalModulation, states["digital_modulation"], self._prefix)
        self._controller.set(Cmd.ExternalPowerControl, states["external_control_mode"], self._prefix)
        self.log.info(f"modulated mode set to {value}")

    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser.
        :rtype: dict
        """
        return self._controller.faults()

    def close(self) -> None:
        """
        Close the laser connection.

        :return: None
        """
        self.disable()
        self.log.info("laser closed")

    @property
    def power_mw(self) -> float:
        """
        Get the current laser power.

        :return: Current laser power in milliwatts.
        :rtype: float
        """
        power_mw = self._controller.get(Query.LaserPower, self._prefix)
        return float(power_mw)

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius.
        :rtype: float
        """
        temperature_c = self._controller.get(Query.BasePlateTemperature)
        return float(temperature_c)

    def _coefficients_curve(self) -> Expr:
        """
        Get the power-current curve as a symbolic expression.

        :return: Power-current curve as a sympy expression.
        :rtype: Expr
        """
        x = symbols("x")
        func: Expr = 0
        for order, co in self._coefficients.items():
            func = func + float(co) * x ** int(order)
        return func

    @property
    def max_power(self) -> float:
        """
        Get the maximum power in milliwatts.

        :return: Maximum power in milliwatts.
        :rtype: float
        """
        return float(self._controller.get(Query.MaximumLaserPower, self._prefix))

    def _set_max_power(self) -> None:
        """
        Set the maximum power property for the power_setpoint_mw descriptor.

        :return: None
        """
        type(self.power_setpoint_mw).maximum = self.max_power

    def _get_constant_current(self) -> BoolVal:
        """
        Get the constant current mode status.

        :return: Constant current mode status.
        :rtype: BoolVal
        """
        return BoolVal(self._controller.get(Query.LaserDriverControlMode, self._prefix))

    def _set_constant_current(self, value: BoolVal) -> None:
        """
        Set the constant current mode status.

        :param value: Desired constant current mode status.
        :type value: BoolVal
        :return: None
        """
        self._controller.set(Cmd.LaserDriverControlMode, value, self._prefix)

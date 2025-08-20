import sys
from enum import Enum
from typing import Dict, Union

from pycobolt import CoboltLaser
from sympy import Expr, solve, symbols

from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.laser.base import BaseLaser

# Define StrEnums if they don't yet exist.
if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        """
        String enumeration class for command and query strings.
        """

        pass

else:
    from enum import StrEnum


class Cmd(StrEnum):
    """
    Command strings for controlling the laser.
    """

    LaserEnable = "l1"  # Enable(1)/Disable(0)
    LaserDisable = "l0"  # Enable(1)/Disable(0)
    EnableModulation = "em"
    ConstantPowerMode = "cp"
    EnableDigitalModulation = "sdmes 1"
    DisableDigitalModulation = "sdmes 0"
    EnableAnalogModulation = "sames 1"
    DisableAnalogModulation = "sames 0"
    PowerSetpoint = "p"
    CurrentSetpoint = "slc"


class Query(StrEnum):
    """
    Query strings for retrieving laser status.
    """

    ModulationMode = "gmes?"
    AnalogModulationMode = "games?"
    DigitalModulationMode = "gdmes?"
    PowerSetpoint = "p?"


# Boolean command value that can also be compared like a boolean.
class BoolVal(StrEnum):
    """
    Boolean command values for laser control.
    """

    OFF = "0"
    ON = "1"


MODULATION_MODES = {
    "off": {
        "external_control_mode": Cmd.ConstantPowerMode,
        "digital_modulation": Cmd.DisableDigitalModulation,
        "analog_modulation": Cmd.DisableAnalogModulation,
    },
    "analog": {
        "external_control_mode": Cmd.EnableModulation,
        "digital_modulation": Cmd.DisableDigitalModulation,
        "analog_modulation": Cmd.EnableAnalogModulation,
    },
    "digital": {
        "external_control_mode": Cmd.EnableModulation,
        "digital_modulation": Cmd.EnableDigitalModulation,
        "analog_modulation": Cmd.DisableAnalogModulation,
    },
}


class SkyraLaser(BaseLaser):
    """
    SkyraLaser class for handling Cobolt Skyra laser devices.
    """

    def __init__(
        self,
        id: str,
        wavelength: int,
        port: str,
        prefix: str,
        max_power_mw: float,
        min_current_ma: float,
        max_current_ma: float,
        coefficients: Dict[str, float],
    ) -> None:
        """
        Initialize the SkyraLaser object.

        :param id: Laser ID
        :type id: str
        :param wavelength: Wavelength in nanometers
        :type wavelength: int
        :param port: Serial port for the laser
        :type port: str
        :param prefix: Command prefix for the laser
        :type prefix: str
        :param max_power_mw: Maximum power in milliwatts
        :type max_power_mw: float
        :param min_current_ma: Minimum current in milliamps
        :type min_current_ma: float
        :param max_current_ma: Maximum current in milliamps
        :type max_current_ma: float
        :param coefficients: Coefficients for the power-current curve
        :type coefficients: dict
        """
        super().__init__(id)

        self._inst = CoboltLaser(port)

        self._prefix = prefix
        self._coefficients = coefficients
        self._min_current_ma = min_current_ma
        self._max_current_ma = max_current_ma
        self._current_setpoint = self._min_current_ma
        self._max_power_mw = max_power_mw
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

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

    def enable(self) -> None:
        """
        Enable the laser.
        """
        self._inst.send_cmd(f"{self._prefix}Cmd.LaserEnable")
        self.log.info(f"laser {self._prefix} enabled")

    def disable(self) -> None:
        """
        Disable the laser.
        """
        self._inst.send_cmd(f"{self._prefix}Cmd.LaserDisable")
        self.log.info(f"laser {self._prefix} disabled")

    @DeliminatedProperty(minimum=0, maximum=lambda self: self.max_power)
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint in milliwatts.

        :return: Power setpoint in milliwatts
        :rtype: float
        """
        if self._inst.constant_current == "ON":
            return int(round(self._coefficients_curve().subs(symbols("x"), self._current_setpoint)))
        else:
            return self._inst.send_cmd(f"{self._prefix}Query.PowerSetpoint") * 1000

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: Union[float, int]) -> None:
        """
        Set the power setpoint in milliwatts.

        :param value: Power setpoint in milliwatts
        :type value: float or int
        """
        if self.modulation_mode != "off":
            # solutions for laser value
            solutions = solve(self._coefficients_curve() - value)
            for sol in solutions:
                # must be within current range
                if round(sol) in range(int(self._min_current_ma), int(self._max_current_ma)):
                    # setpoint must be integer
                    self._current_setpoint = int(round(sol))
                    # set laser current setpoint to ma value
                    self._inst.send_cmd(f"{self._prefix}Cmd.CurrentSetpoint {self._current_setpoint}")
                    return
            # if no value exists, alert user
            self.log.error(f"Cannot set laser to {value} mW because no current mA correlates to {value} mW")
        else:
            # convert from mw to watts
            self._inst.send_cmd(f"{self._prefix}Cmd.PowerSetpoint {value / 1000}")
        self.log.info(f"laser {self._prefix} set to {value} mW")

    @property
    def modulation_mode(self) -> str:
        """
        Get the modulation mode.

        :return: Modulation mode
        :rtype: str
        """
        # query the laser for the modulation mode
        if self._inst.send_cmd(f"{self._prefix}Query.ModulationMode") == BoolVal.OFF:
            return "off"
        elif self._inst.send_cmd(f"{self._prefix}Query.AnalogModulationMode") == BoolVal.ON:
            return "analog"
        else:
            return "digital"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """
        Set the modulation mode.

        :param value: Modulation mode
        :type value: str
        :raises ValueError: If the modulation mode is not valid
        """
        if value not in MODULATION_MODES:
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        external_control_mode = MODULATION_MODES[value]["external_control_mode"]
        digital_modulation = MODULATION_MODES[value]["digital_modulation"]
        analog_modulation = MODULATION_MODES[value]["analog_modulation"]
        self._inst.send_cmd(f"{self._prefix}{external_control_mode}")
        self._inst.send_cmd(f"{self._prefix}{digital_modulation}")
        self._inst.send_cmd(f"{self._prefix}{analog_modulation}")
        self.log.info(f"modulation mode set to {value}")

    def close(self) -> None:
        """
        Close the laser connection.
        """
        self.log.info("closing and calling disable")
        self.disable()
        if self._inst.is_connected():
            self._inst.disconnect()

    @property
    def power_mw(self) -> float:
        """
        Get the current power in milliwatts.

        :return: Current power in milliwatts
        :rtype: float
        """
        return self._inst.get_power()

    @property
    def temperature_c(self) -> Union[float, None]:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return None

    @property
    def max_power(self) -> float:
        """
        Get the maximum power in milliwatts.

        :return: Maximum power in milliwatts
        :rtype: float
        """
        if self._inst.constant_current == "ON":
            return int((round(self._coefficients_curve().subs(symbols("x"), 100), 1)))
        else:
            return int(self._max_power_mw)

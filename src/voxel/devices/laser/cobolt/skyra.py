import sys
from enum import Enum

from pycobolt import CoboltLaser
from sympy import Expr, solve, symbols

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser

# Define StrEnums if they don't yet exist.
if sys.version_info < (3, 11):

    class StrEnum(str, Enum):
        pass

else:
    from enum import StrEnum


class Cmd(StrEnum):
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
    ModulationMode = "gmes?"
    AnalogModulationMode = "games?"
    DigitalModulationMode = "gdmes?"
    PowerSetpoint = "p?"


# Boolean command value that can also be compared like a boolean.
class BoolVal(StrEnum):
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

    def __init__(
        self,
        id: str,
        wavelength: int,
        port: str,
        prefix: str,
        max_power_mw: float,
        min_current_ma: float,
        max_current_ma: float,
        coefficients: dict,
    ):
        """
        Communicate with Skyra Cobolt laser.

        :param port: comm port for lasers.
        :param wavelength: wavelength of laser
        :param prefix: prefix specic to laser.
        :param max_power_mw: maximum power in mW
        :param coefficients: polynomial coefficients describing
        the relationship between current mA and power mW
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
        return self._wavelength

    def _coefficients_curve(self) -> Expr:
        x = symbols("x")
        func: Expr = x
        for order, co in self._coefficients.items():
            func = func + float(co) * x ** int(order)
        return func

    def enable(self):
        self._inst.send_cmd(f"{self._prefix}Cmd.LaserEnable")
        self.log.info(f"laser {self._prefix} enabled")

    def disable(self):
        self._inst.send_cmd(f"{self._prefix}Cmd.LaserDisable")
        self.log.info(f"laser {self._prefix} enabled")

    @DeliminatedProperty(minimum=0, maximum=lambda self: self.max_power)
    def power_setpoint_mw(self):
        if self._inst.constant_current == "ON":
            return int(round(self._coefficients_curve().subs(symbols("x"), self._current_setpoint)))
        else:
            return self._inst.send_cmd(f"{self._prefix}Query.PowerSetpoint") * 1000

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float or int):
        if self.modulation_mode != "off":
            # solutions for laser value
            solutions = solve(self._coefficients_curve() - value)
            for sol in solutions:
                # must be within current range
                if round(sol) in range(int(self._min_current_ma), int(self._max_current_ma)):
                    # setpoint must be integer
                    self._current_setpoint = int(round(sol))
                    # set lasser current setpoint to ma value
                    self._inst.send_cmd(f"{self._prefix}Cmd.CurrentSetpoint" f"{self._current_setpoint}")
                    return
            # if no value exists, alert user
            self.log.error(f"Cannot set laser to {value} mW because " f"no current mA correlates to {value} mW")
        else:
            # convert from mw to watts
            self._inst.send_cmd(f"{self._prefix}Cmd.PowerSetpoint {value / 1000}")
        self.log.info(f"laser {self._prefix} set to {value} mW")

    @property
    def modulation_mode(self):
        # query the laser for the modulation mode
        if self._inst.send_cmd(f"{self._prefix}Query.ModulationMode") == BoolVal.OFF:
            return "off"
        elif self._inst.send_cmd(f"{self._prefix}Query.AnalogModulationMode") == BoolVal.ON:
            return "analog"
        else:
            return "digital"

    @modulation_mode.setter
    def modulation_mode(self, value: str):
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        external_control_mode = MODULATION_MODES[value]["external_control_mode"]
        digital_modulation = MODULATION_MODES[value]["digital_modulation"]
        analog_modulation = MODULATION_MODES[value]["analog_modulation"]
        self._inst.send_cmd(f"{self._prefix}{external_control_mode}")
        self._inst.send_cmd(f"{self._prefix}{digital_modulation}")
        self._inst.send_cmd(f"{self._prefix}{analog_modulation}")
        self.log.info(f"modulation mode set to {value}")

    def close(self):
        self.log.info("closing and calling disable")
        self.disable()
        if self._inst.is_connected():
            self._inst.disconnect()

    @property
    def power_mw(self) -> float:
        return self._inst.get_power()

    @property
    def temperature_c(self):
        return None

    @property
    def max_power(self):
        if self._inst.constant_current == "ON":
            return int((round(self._coefficients_curve().subs(symbols("x"), 100), 1)))
        else:
            return int(self._max_power_mw)

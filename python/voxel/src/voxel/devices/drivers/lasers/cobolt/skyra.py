from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, cast

from pycobolt import CoboltLaser
from sympy import (
    Add,
    Eq,
    Mul,
    Pow,
    S,
    Symbol,
    lambdify,
    solve,
)

from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float


class Cmd(StrEnum):
    LaserEnable = 'l1'  # Enable(1)
    LaserDisable = 'l0'  # Disable(0)
    EnableModulation = 'em'
    ConstantPowerMode = 'cp'
    EnableDigitalModulation = 'sdmes 1'
    DisableDigitalModulation = 'sdmes 0'
    EnableAnalogModulation = 'sames 1'
    DisableAnalogModulation = 'sames 0'
    PowerSetpoint = 'p'
    CurrentSetpoint = 'slc'


class Query(StrEnum):
    ModulationMode = 'gmes?'
    AnalogModulationMode = 'games?'
    DigitalModulationMode = 'gdmes?'
    PowerSetpoint = 'p?'


# Boolean command value that can also be compared like a boolean.
class BoolVal(StrEnum):
    OFF = '0'
    ON = '1'


MODULATION_MODES = {
    'off': {
        'external_control_mode': Cmd.ConstantPowerMode,
        'digital_modulation': Cmd.DisableDigitalModulation,
        'analog_modulation': Cmd.DisableAnalogModulation,
    },
    'analog': {
        'external_control_mode': Cmd.EnableModulation,
        'digital_modulation': Cmd.DisableDigitalModulation,
        'analog_modulation': Cmd.EnableAnalogModulation,
    },
    'digital': {
        'external_control_mode': Cmd.EnableModulation,
        'digital_modulation': Cmd.EnableDigitalModulation,
        'analog_modulation': Cmd.DisableAnalogModulation,
    },
}


class SkyraLaser(VoxelLaser):
    """Driver for a Cobolt Skyra module (multi-line Cobolt laser) using pycobolt.

    The polynomial defined by `coefficients` maps drive current (mA) -> optical power (mW).
    Keys are polynomial orders (0,1,2,...) and values are coefficients in mW units.
    Example: {"0": 0.0, "1": 0.12, "2": 0.0003}
    """

    def __init__(
        self,
        name: str,
        wavelength: int,
        port: str,
        prefix: str,
        max_power_mw: float,
        min_current_ma: float,
        max_current_ma: float,
        coefficients: Mapping[int | str, float],
    ):
        """Communicate with a Cobolt Skyra laser.

        :param name: Logical name of the laser line.
        :param wavelength: Wavelength (nm) of the laser line.
        :param port: Serial/USB COM port (e.g., 'COM3' or '/dev/ttyUSB0').
        :param prefix: String prefix for this laser line (device-specific addressing).
        :param max_power_mw: Maximum allowed power (mW) in constant-power mode.
        :param min_current_ma: Minimum allowed drive current (mA).
        :param max_current_ma: Maximum allowed drive current (mA).
        :param coefficients: Polynomial coefficients mapping current (mA) -> power (mW).
        """
        super().__init__(name=name, wavelength=wavelength)

        self._inst = CoboltLaser(port)
        self._prefix = prefix

        self._min_current_ma = float(min_current_ma)
        self._max_current_ma = float(max_current_ma)
        self._current_setpoint = self._min_current_ma  # mA
        self._max_power_mw = float(max_power_mw)

        # --- Polynomial setup (current mA -> power mW) ---
        self._coefficients = dict(coefficients)
        self._x: Symbol = Symbol('x', real=True)

        # Use SymPy constructors (Add/Mul/Pow) to avoid operator typing issues with static checkers.
        self._poly_expr: Any = S.Zero  # SymPy expression (type Any to keep Pylance happy)
        for order, co in self._coefficients.items():
            # term = S(float(co)) * (self._x ** int(order))
            term_any: Any = Mul(S(float(co)), Pow(self._x, int(order)))
            self._poly_expr = Add(self._poly_expr, term_any)

        # Fast numeric function: returns plain Python float
        self._poly_fn: Callable[[float], float] = cast(
            'Callable[[float], float]',
            lambdify(self._x, self._poly_expr, 'math'),
        )

    # ----------------------- Helpers -----------------------

    def _poly_mw(self, current_ma: float) -> float:
        """Evaluate the polynomial in mW for a given drive current (mA)."""
        return float(self._poly_fn(float(current_ma)))

    @staticmethod
    def _is_on(value: object) -> bool:
        """Robustly interpret device boolean-ish responses."""
        s = str(value).strip().upper()
        return s in {'1', 'ON', 'TRUE'}

    @staticmethod
    def _is_off(value: object) -> bool:
        s = str(value).strip().upper()
        return s in {'0', 'OFF', 'FALSE'}

    def _cc_on(self) -> bool:
        """Is the device in constant-current mode? (best-effort)."""
        try:
            return self._is_on(self._inst.constant_current)
        except Exception:
            # Fallback: assume constant-power if unknown
            self.log.exception('Error checking constant-current mode')
            return False

    def _coefficients_curve(self):
        """Return the symbolic polynomial (compat shim for older code)."""
        return self._poly_expr

    # ----------------------- Commands -----------------------

    def enable(self):
        self._inst.send_cmd(f'{self._prefix}{Cmd.LaserEnable.value}')
        self.log.info('laser %s enabled', self._prefix)

    def disable(self):
        self._inst.send_cmd(f'{self._prefix}{Cmd.LaserDisable.value}')
        self.log.info('laser %s disabled', self._prefix)

    @deliminated_float(min_value=0, max_value=lambda self: self.max_power)
    def power_setpoint_mw(self):
        """In constant-current mode, report the polynomial-evaluated power (mW) for the
        current setpoint. In constant-power mode, query the device setpoint and
        convert to mW.
        """
        if self._cc_on():
            return round(self._poly_mw(self._current_setpoint))
        watts = float(self._inst.send_cmd(f'{self._prefix}{Query.PowerSetpoint.value}'))
        return watts * 1000.0

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float):
        """Setting the power behaves differently depending on modulation mode:
        - If modulation_mode != "off" (i.e., external modulation / current control),
          we solve the polynomial for a valid current in [min_current, max_current].
        - If modulation_mode == "off" (constant-power mode), we send the setpoint in Watts.
        """
        value = float(value)
        if self.modulation_mode != 'off':
            # Use Eq(...) to avoid Expr - float type issues in the type-checker
            sols = solve(Eq(self._poly_expr, S(value)), self._x)
            for sol in sols:
                # Only consider real roots
                if getattr(sol, 'is_real', None) is False:
                    continue
                try:
                    cur = float(sol)
                except TypeError:
                    cur = float(sol.evalf())
                if self._min_current_ma <= cur <= self._max_current_ma:
                    self._current_setpoint = float(round(cur))  # integer mA
                    self._inst.send_cmd(f'{self._prefix}{Cmd.CurrentSetpoint.value} {int(self._current_setpoint)}')
                    self.log.info(
                        'laser %s set to %.3f mW via current ≈ %d mA',
                        self._prefix,
                        value,
                        int(self._current_setpoint),
                    )
                    return

            self.log.error(
                'Cannot set laser to %.3f mW: no valid current in [%.1f, %.1f] mA solves the polynomial.',
                value,
                self._min_current_ma,
                self._max_current_ma,
            )
        else:
            # Constant-power mode expects Watts
            self._inst.send_cmd(f'{self._prefix}{Cmd.PowerSetpoint.value} {value / 1000.0}')
            self.log.info('laser %s set to %.3f mW', self._prefix, value)

    @property
    def modulation_mode(self) -> str:
        """Returns one of {"off", "analog", "digital"} based on device queries."""
        mod = self._inst.send_cmd(f'{self._prefix}{Query.ModulationMode.value}')
        if self._is_off(mod):
            return 'off'

        am = self._inst.send_cmd(f'{self._prefix}{Query.AnalogModulationMode.value}')
        if self._is_on(am):
            return 'analog'

        return 'digital'

    @modulation_mode.setter
    def modulation_mode(self, value: str):
        if value not in MODULATION_MODES:
            msg = f'mode must be one of {tuple(MODULATION_MODES.keys())}.'
            raise ValueError(msg)
        cfg = MODULATION_MODES[value]
        self._inst.send_cmd(f'{self._prefix}{cfg["external_control_mode"].value}')
        self._inst.send_cmd(f'{self._prefix}{cfg["digital_modulation"].value}')
        self._inst.send_cmd(f'{self._prefix}{cfg["analog_modulation"].value}')
        self.log.info('modulation mode set to %s', value)

    def close(self):
        self.log.info('closing and calling disable')
        try:
            self.disable()
        finally:
            try:
                if self._inst.is_connected():
                    self._inst.disconnect()
            except Exception:
                self.log.exception('Error disconnecting instrument')

    # ----------------------- Telemetry -----------------------

    @property
    def power_mw(self) -> float:
        """Return measured power as reported by device library (units per pycobolt)."""
        return self._inst.get_power()

    @property
    def temperature_c(self):
        # Not available from this device via this driver
        return None

    @property
    def max_power(self) -> int:
        """Maximum allowed power (mW) for the current control scheme.
        In current-control, estimate from polynomial at max current.
        In constant-power, use the configured max power.
        """
        if self._cc_on():
            return round(self._poly_mw(self._max_current_ma))
        return int(self._max_power_mw)

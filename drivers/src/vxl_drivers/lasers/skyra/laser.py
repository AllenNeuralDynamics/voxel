"""One Cobolt Skyra laser line, with software and analog control."""

from math import isfinite
from time import monotonic, sleep
from typing import ClassVar

from rigup.device import fact, stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light.base import ControlMode
from vxl.devices.light.laser import Laser
from vxl_drivers.lasers.skyra.hub import SkyraError, SkyraHub

_WAVELENGTH_MATCH_NM = 5.0
# Digital modulation sets its on-level as a current (#smc), so it waits for a measured current-to-power curve.
# In analog mode, 1 V gives the line's rated power and the power setpoint has no effect.
# Line 1 (DPL) moves to a different TEC3 temperature in modulation mode; let it settle before imaging.
_MODE_COMMANDS: dict[ControlMode, tuple[str, ...]] = {
    "software": ("cp",),
    "analog": ("em", "sdmes 0", "sames 1"),
}


class SkyraLaser(Laser):
    """One line of a Skyra, with its power in mW. :meth:`on` waits out the startup delay.

    It does software and analog control, so it has only an analog pin. The line changes its control mode only while
    it is off, so a change while it is on turns it off, changes the mode, and turns it on again."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        uid: str,
        hub: SkyraHub,
        line: int,
        wavelength: float,
        *,
        max_power_mw: float,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 0.1,
    ) -> None:
        super().__init__(uid=uid)
        if isinstance(line, bool) or not isinstance(line, int):
            raise ValueError("line must be an integer")
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not isfinite(max_power_mw) or max_power_mw <= 0:
            raise ValueError("maximum power must be finite and positive")
        if not isfinite(startup_delay_s) or startup_delay_s < 0:
            raise ValueError("startup delay must be finite and nonnegative")
        if not isfinite(setpoint_tolerance_mw) or setpoint_tolerance_mw <= 0:
            raise ValueError("setpoint tolerance must be finite and positive")
        self._wavelength = float(wavelength)
        self._range = Span(0.0, float(max_power_mw))
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._enabled_at: float | None = None
        self._closed = False
        self._hub = hub
        self._line = line
        hub.reserve(line, uid)
        try:
            self._initialize()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("Skyra initialization and inhibition failed", [error, cleanup_error]) from None
            hub.release(line, uid)
            raise
        self.log.info(f"Initialized Skyra line {line}: {self._wavelength} nm, max_power={max_power_mw} mW")

    def _initialize(self) -> None:
        reported = self._hub.installed_lines[self._line]
        if abs(reported - self._wavelength) > _WAVELENGTH_MATCH_NM:
            raise ValueError(f"Skyra line {self._line} reports {reported} nm, but {self._wavelength} nm is configured")
        with self._hub.transaction():
            self.off()
            self._write_control_mode("software")
            # Adopt the existing target within the configured range and resolution.
            self._set_power(min(self._hub.number(self._cmd("p?")) * 1000, self._range.high))

    def _cmd(self, command: str) -> str:
        return f"{self._line}{command}"

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        return self._hub.number(self._cmd("p?")) * 1000

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        if self._closed or self._hub.confirmed_off(self._line):
            return False
        return self._hub.flag(self._cmd("l?"))

    # TODO: verify on real hardware whether #gam? reports constant current per line; #gmes? 0 cannot tell cp from ci.
    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        with self._hub.transaction():
            if not self._hub.flag(self._cmd("gmes?")):
                return "software"
            analog = self._hub.flag(self._cmd("games?"))
            digital = self._hub.flag(self._cmd("gdmes?"))
        if analog and not digital:
            return "analog"
        raise SkyraError(f"Skyra line {self._line} modulation was set outside this driver")

    @property
    def pins(self) -> list[Pin]:
        return [Pin(name="analog_in", direction="in", kind="analog")]

    def on(self) -> None:
        self._ensure_open()
        try:
            with self._hub.transaction():
                if not self.is_on:
                    self._hub.set_line(self._line, True)
                    self._enabled_at = monotonic()
            # Wait outside the transaction so other lines stay available.
            self._wait_for_startup()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("Skyra enable and inhibition failed", [error, cleanup_error]) from None
            raise

    def _wait_for_startup(self) -> None:
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_on:
            raise SkyraError(f"Skyra line {self._line} switched off during startup")

    def off(self) -> None:
        if self._closed or self._hub.confirmed_off(self._line):
            return
        self._hub.set_line(self._line, False)
        self._enabled_at = None

    # TODO: verify on real hardware the setpoint resolution of #p and whether #p is accepted in modulation mode.
    def _set_power(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("power must be finite")
        with self._hub.transaction():
            self._hub.command(self._cmd(f"p {value / 1000:.5f}"))
            readback = self._hub.number(self._cmd("p?")) * 1000
            if abs(readback - value) > self._setpoint_tolerance_mw:
                raise SkyraError(f"Skyra line {self._line} power setpoint reads {readback} mW after setting {value} mW")

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode not in _MODE_COMMANDS:
            raise ValueError(f"{self.uid} does not do {mode} control")
        with self._hub.transaction():
            if self.control_mode == mode:
                return
            was_on = self.is_on
            if was_on:
                self.off()
            self._write_control_mode(mode)
        if was_on:
            self.on()

    def _write_control_mode(self, mode: ControlMode) -> None:
        with self._hub.transaction():
            for command in _MODE_COMMANDS[mode]:
                self._hub.command(self._cmd(command))
            if self.control_mode != mode:
                raise SkyraError(f"Skyra line {self._line} did not establish {mode} control")

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._hub.number(self._cmd("pa?")) * 1000

    @property
    @fact(label="Line")
    def line(self) -> int:
        return self._line

    @property
    @stream("slow", label="Diode Current", units="mA")
    def diode_current_ma(self) -> float:
        self._ensure_open()
        return self._hub.number(self._cmd("i?"))

    @property
    @stream("slow", label="In Autostart")
    def in_autostart(self) -> bool:
        """Whether the autostart sequence includes this line."""
        self._ensure_open()
        return self._hub.flag(self._cmd("gla?"))

    def dispose(self) -> None:
        """Switch the line off and release it; the rig closes the hub."""
        if self._closed:
            return
        self.off()
        self._hub.release(self._line, self.uid)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Skyra laser is closed")

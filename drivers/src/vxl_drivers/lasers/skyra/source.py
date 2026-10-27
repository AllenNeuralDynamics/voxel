"""One Cobolt Skyra laser line with software and analog modulation."""

from math import isfinite
from time import monotonic, sleep

from rigup import describe, numeric
from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl_drivers.lasers.skyra.controller import SkyraController, SkyraError

_WAVELENGTH_MATCH_NM = 5.0
# Digital modulation sets its on-level as a current (#smc), so it waits for a measured current-to-power curve.
# In analog mode, 1 V gives the line's rated power and the power setpoint has no effect.
# Line 1 (DPL) moves to a different TEC3 temperature in modulation mode; let it settle before imaging.
_MODE_COMMANDS = {
    ModulationMode.SOFTWARE: ("cp",),
    ModulationMode.ANALOG: ("em", "sdmes 0", "sames 1"),
}


class SkyraSource(LaserSource):
    """Borrow one Skyra line; wrap with SourceOnlyLaser for source-scaled output."""

    def __init__(
        self,
        uid: str,
        controller: SkyraController,
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
        self._max_power_mw = max_power_mw
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._enabled_at: float | None = None
        self._closed = False
        self._controller = controller
        self._line = line
        controller.reserve(line, uid)
        try:
            self._initialize()
        except Exception as error:
            try:
                self.source_disable()
            except Exception as cleanup_error:
                raise ExceptionGroup("Skyra initialization and inhibition failed", [error, cleanup_error]) from None
            controller.release(line, uid)
            raise
        self.log.info(f"Initialized Skyra line {line}: {self._wavelength} nm, max_power={max_power_mw} mW")

    def _initialize(self) -> None:
        reported = self._controller.installed_lines[self._line]
        if abs(reported - self._wavelength) > _WAVELENGTH_MATCH_NM:
            raise ValueError(f"Skyra line {self._line} reports {reported} nm, but {self._wavelength} nm is configured")
        with self._controller.transaction():
            self.source_disable()
            self._configure_modulation_mode(ModulationMode.SOFTWARE)
            # Adopt the existing target within the configured range and resolution.
            self.source_power_setpoint_mw = min(self._controller.number(self._cmd("p?")) * 1000, self._max_power_mw)

    def _cmd(self, command: str) -> str:
        return f"{self._line}{command}"

    @property
    def wavelength(self) -> float:
        """Configured nominal wavelength of the installed line."""
        return self._wavelength

    def source_enable(self, *, wait: bool = False) -> None:
        """Switch the line on; optionally wait out the configured startup delay."""
        self._ensure_open()
        try:
            with self._controller.transaction():
                if not self.is_source_enabled:
                    self._controller.set_line(self._line, True)
                    self._enabled_at = monotonic()
            # Wait outside the transaction so other lines stay available.
            if wait:
                self._wait_for_startup()
        except Exception as error:
            try:
                self.source_disable()
            except Exception as cleanup_error:
                raise ExceptionGroup("Skyra enable and inhibition failed", [error, cleanup_error]) from None
            raise

    def _wait_for_startup(self) -> None:
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_source_enabled:
            raise SkyraError(f"Skyra line {self._line} switched off during startup")

    def source_disable(self) -> None:
        if self._closed or self._controller.confirmed_off(self._line):
            return
        self._controller.set_line(self._line, False)
        self._enabled_at = None

    @property
    def is_source_enabled(self) -> bool:
        if self._closed or self._controller.confirmed_off(self._line):
            return False
        return self._controller.flag(self._cmd("l?"))

    # TODO: verify on real hardware the setpoint resolution of #p and whether #p is accepted in modulation mode.
    @numeric(minimum=0.0, maximum=lambda self: self._max_power_mw, step=0.1)
    def source_power_setpoint_mw(self) -> float:
        self._ensure_open()
        return self._controller.number(self._cmd("p?")) * 1000

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("source power must be finite")
        with self._controller.transaction():
            self._controller.command(self._cmd(f"p {value / 1000:.5f}"))
            readback = self._controller.number(self._cmd("p?")) * 1000
            if abs(readback - value) > self._setpoint_tolerance_mw:
                raise SkyraError(f"Skyra line {self._line} power setpoint reads {readback} mW after setting {value} mW")

    @property
    def source_power_mw(self) -> float:
        self._ensure_open()
        return self._controller.number(self._cmd("pa?")) * 1000

    @property
    @describe(label="Line")
    def line(self) -> int:
        return self._line

    @property
    @describe(label="Diode Current", units="mA")
    def diode_current_ma(self) -> float:
        self._ensure_open()
        return self._controller.number(self._cmd("i?"))

    @property
    @describe(label="In Autostart")
    def in_autostart(self) -> bool:
        """Whether the autostart sequence includes this line."""
        self._ensure_open()
        return self._controller.flag(self._cmd("gla?"))

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(_MODE_COMMANDS)

    # TODO: verify on real hardware whether #gam? reports constant current per line; #gmes? 0 cannot tell cp from ci.
    def _read_modulation_mode(self) -> ModulationMode:
        self._ensure_open()
        with self._controller.transaction():
            if not self._controller.flag(self._cmd("gmes?")):
                return ModulationMode.SOFTWARE
            analog = self._controller.flag(self._cmd("games?"))
            digital = self._controller.flag(self._cmd("gdmes?"))
        if analog and not digital:
            return ModulationMode.ANALOG
        raise SkyraError(f"Skyra line {self._line} modulation was set outside this driver")

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        if mode not in _MODE_COMMANDS:
            raise ValueError(f"SkyraSource does not support {mode} modulation")
        with self._controller.transaction():
            self._ensure_modulation_change_allowed()
            for command in _MODE_COMMANDS[mode]:
                self._controller.command(self._cmd(command))
            if self._read_modulation_mode() != mode:
                raise SkyraError(f"Skyra line {self._line} did not establish {mode} modulation")

    def close(self) -> None:
        """Switch the line off and release it; the rig owns controller teardown."""
        if self._closed:
            return
        self.source_disable()
        self._controller.release(self._line, self.uid)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Skyra source is closed")

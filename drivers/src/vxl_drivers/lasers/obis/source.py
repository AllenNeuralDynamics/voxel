"""Coherent OBIS LX or LS source, on its own port or one controller channel."""

from collections.abc import Mapping
from math import isfinite
from time import monotonic, sleep
from typing import TypedDict

from rigup import describe, numeric
from vxl.devices.laser.source import LaserSource, ModulationMode
from vxl_drivers.lasers.obis.controller import ObisController
from vxl_drivers.lasers.obis.link import ObisError, ObisLink

_CDRH_DELAY_S = 5.0
_WAVELENGTH_MATCH_NM = 5.0
# TODO: verify on real hardware that 5 V analog input means the laser's maximum power, not the setpoint.
# TODO: verify on real hardware that an LX turns fully off when its digital input is low.
_MODE_COMMANDS = {
    ModulationMode.SOFTWARE: "AM:INT CWP",
    ModulationMode.DIGITAL: "AM:EXT DIG",
    ModulationMode.ANALOG: "AM:EXT ANAL",
}
# CWC, MIXED, and the LX-only DIGSO and MIXSO are outside this interface.
_MODE_REPLIES = {"CWP": ModulationMode.SOFTWARE, "DIGITAL": ModulationMode.DIGITAL, "ANALOG": ModulationMode.ANALOG}


class ObisChannel(TypedDict):
    """A controller channel for ObisSource's conn argument."""

    controller: ObisController
    channel: int


class ObisSource(LaserSource):
    """Pass a port name as conn, or {controller, channel}; wrap with SourceOnlyLaser."""

    def __init__(
        self,
        uid: str,
        conn: str | ObisChannel,
        wavelength: float,
        *,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 0.05,
        baud: int = 115200,
    ) -> None:
        super().__init__(uid=uid)
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not isfinite(startup_delay_s) or startup_delay_s < 0:
            raise ValueError("startup delay must be finite and nonnegative")
        if not isfinite(setpoint_tolerance_mw) or setpoint_tolerance_mw <= 0:
            raise ValueError("setpoint tolerance must be finite and positive")
        self._wavelength = float(wavelength)
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._min_power_mw = 0.0
        self._max_power_mw = 0.0
        self._enabled_at: float | None = None
        self._closed = False
        if isinstance(conn, str):
            self._controller: ObisController | None = None
            self._channel: int | None = None
            self._address = ""
            self._link = ObisLink(conn, baud=baud)
        else:
            self._controller, self._channel = _parse_channel(conn)
            self._address = str(self._channel)
            self._link = self._controller.link
            self._controller.reserve(self._channel, uid)
        try:
            self._initialize()
        except Exception as error:
            try:
                self.source_disable()
            except Exception as cleanup_error:
                if self._controller is None:
                    self._link.close()
                raise ExceptionGroup("OBIS initialization and inhibition failed", [error, cleanup_error]) from None
            self._release_connection()
            raise
        self.log.info(f"Initialized OBIS: model={self._model}, max_power={self._max_power_mw} mW")

    def _initialize(self) -> None:
        with self._link.transaction():
            reported = self._link.number(self._syst("INF:WAV?"))
            if abs(reported - self._wavelength) > _WAVELENGTH_MATCH_NM:
                raise ValueError(f"OBIS reports {reported} nm, but {self._wavelength} nm is configured")
            self._model = self._link.query(self._syst("INF:MOD?"))
            self._serial_number = self._link.query(self._syst("INF:SNUM?"))
            self.source_disable()
            self._min_power_mw = self._link.number(self._sour("POW:LIM:LOW?")) * 1000
            self._max_power_mw = self._link.number(self._sour("POW:LIM:HIGH?")) * 1000
            if not 0 <= self._min_power_mw < self._max_power_mw:
                raise ObisError(f"Invalid OBIS power limits {self._min_power_mw}..{self._max_power_mw} mW")
            self._configure_modulation_mode(ModulationMode.SOFTWARE)
            # Adopt the existing target within the firmware range and resolution.
            self.source_power_setpoint_mw = self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000
            if self.autostart:
                self.log.warning("OBIS autostart is on: the laser emits at power-up")

    def _sour(self, command: str) -> str:
        return f"SOUR{self._address}:{command}"

    def _syst(self, command: str) -> str:
        return f"SYST{self._address}:{command}"

    @property
    def wavelength(self) -> float:
        """Configured nominal wavelength of the installed source."""
        return self._wavelength

    def source_enable(self, *, wait: bool = False) -> None:
        """Enable emission; optionally wait out the CDRH delay and configured startup delay."""
        self._ensure_open()
        try:
            with self._link.transaction():
                if not self.is_source_enabled:
                    self._link.set_emission(self._address, True)
                    self._enabled_at = monotonic()
            # Wait outside the transaction so other channels on a controller stay available.
            if wait:
                self._wait_for_startup()
        except Exception as error:
            try:
                self.source_disable()
            except Exception as cleanup_error:
                raise ExceptionGroup("OBIS enable and inhibition failed", [error, cleanup_error]) from None
            raise

    def _wait_for_startup(self) -> None:
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        delay = self._startup_delay_s + (_CDRH_DELAY_S if self.cdrh_delay else 0.0)
        remaining = delay - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_source_enabled:
            raise ObisError("OBIS emission permission was lost during startup")

    def source_disable(self) -> None:
        if self._closed or self._confirmed_off():
            return
        self._link.set_emission(self._address, False)
        self._enabled_at = None

    @property
    def is_source_enabled(self) -> bool:
        if self._closed or self._confirmed_off():
            return False
        return self._link.flag(self._sour("AM:STAT?"))

    # TODO: verify on real hardware the setpoint resolution; the wire format allows 0.01 mW (5 decimals in W).
    @numeric(minimum=lambda self: self._min_power_mw, maximum=lambda self: self._max_power_mw, step=0.01)
    def source_power_setpoint_mw(self) -> float:
        self._ensure_open()
        return self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000

    @source_power_setpoint_mw.setter
    def source_power_setpoint_mw(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("source power must be finite")
        with self._link.transaction():
            self._link.command(self._sour(f"POW:LEV:IMM:AMPL {value / 1000:.5f}"))
            readback = self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000
            if abs(readback - value) > self._setpoint_tolerance_mw:
                raise ObisError(f"OBIS power setpoint reads {readback} mW after setting {value} mW")

    @property
    def source_power_mw(self) -> float:
        self._ensure_open()
        return self._link.number(self._sour("POW:LEV?")) * 1000

    @property
    def temperature_c(self) -> float:
        """Base plate temperature."""
        self._ensure_open()
        return self._link.number(self._sour("TEMP:BAS?"), suffix="C")

    @property
    @describe(label="Model")
    def model(self) -> str:
        return self._model

    @property
    @describe(label="Serial Number")
    def serial_number(self) -> str:
        return self._serial_number

    @property
    @describe(label="Operating Hours")
    def operating_hours(self) -> str:
        """Reply to SYST:HOUR?, unparsed until its format is confirmed."""
        self._ensure_open()
        return self._link.query(self._syst("HOUR?"))

    @property
    @describe(label="CDRH Delay")
    def cdrh_delay(self) -> bool:
        """Whether emission starts 5 s after enable."""
        self._ensure_open()
        return self._link.flag(self._syst("CDRH?"))

    @property
    @describe(label="Autostart")
    def autostart(self) -> bool:
        """Whether the laser emits at power-up."""
        self._ensure_open()
        return self._link.flag(self._syst("AUT?"))

    @property
    @describe(label="Interlock")
    def interlock(self) -> str:
        """Reply to SYST:LOCK?, unparsed until its meaning is confirmed."""
        # TODO: verify on real hardware what SYST:LOCK? replies with the interlock open and closed.
        self._ensure_open()
        return self._link.query(self._syst("LOCK?"))

    @property
    @describe(label="Status Code")
    def status_code(self) -> str:
        """Hex status bits from SYST:STAT?."""
        self._ensure_open()
        return self._link.query(self._syst("STAT?"))

    @property
    @describe(label="Fault Code")
    def fault_code(self) -> str:
        """Hex fault bits from SYST:FAUL?; 00000000 means no fault."""
        # TODO: verify on real hardware what bit 31 (80000000) means; one lab saw it with no fault.
        self._ensure_open()
        return self._link.query(self._syst("FAUL?"))

    def _get_modulation_modes(self) -> tuple[ModulationMode, ...]:
        return tuple(ModulationMode)

    def _read_modulation_mode(self) -> ModulationMode:
        self._ensure_open()
        reply = self._link.query(self._sour("AM:SOUR?"))
        if (mode := _MODE_REPLIES.get(reply.upper())) is None:
            raise ObisError(f"OBIS mode {reply!r} was set outside this driver")
        return mode

    def _configure_modulation_mode(self, mode: ModulationMode) -> None:
        self._ensure_open()
        with self._link.transaction():
            self._ensure_modulation_change_allowed()
            self._link.command(self._sour(_MODE_COMMANDS[mode]))
            if self._read_modulation_mode() != mode:
                raise ObisError(f"OBIS did not establish {mode} modulation")

    def close(self) -> None:
        """Disable emission, then close the port or release the channel; failures can be retried."""
        if self._closed:
            return
        self.source_disable()
        self._release_connection()
        self._closed = True

    def _release_connection(self) -> None:
        if self._controller is None:
            self._link.close()
        elif self._channel is not None:
            self._controller.release(self._channel, self.uid)

    def _confirmed_off(self) -> bool:
        if self._controller is None or self._channel is None:
            return False
        return self._controller.confirmed_off(self._channel)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("OBIS source is closed")


def _parse_channel(conn: Mapping[str, object]) -> tuple[ObisController, int]:
    if set(conn) != {"controller", "channel"}:
        raise ValueError("conn must be a serial port name or {controller, channel}")
    controller, channel = conn["controller"], conn["channel"]
    if not isinstance(controller, ObisController):
        raise ValueError(f"controller {controller!r} is not an ObisController device")
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ValueError("channel must be an integer")
    return controller, channel

"""Coherent OBIS LX or LS laser, on its own port or on 1 channel of a hub."""

from collections.abc import Mapping
from math import isfinite
from time import monotonic, sleep
from typing import ClassVar, TypedDict

from rigup.device import fact, stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light import ControlMode, Laser
from vxl_drivers.lasers.obis.hub import ObisHub
from vxl_drivers.lasers.obis.link import ObisError, ObisLink

_CDRH_DELAY_S = 5.0
_WAVELENGTH_MATCH_NM = 5.0
# TODO: verify on real hardware that 5 V analog input means the laser's maximum power, not the setpoint.
# TODO: verify on real hardware that an LX turns fully off when its digital input is low.
_MODE_COMMANDS: dict[ControlMode, str] = {
    "software": "AM:INT CWP",
    "digital": "AM:EXT DIG",
    "analog": "AM:EXT ANAL",
}
# CWC, MIXED, and the LX-only DIGSO and MIXSO are outside this driver.
_MODE_REPLIES: dict[str, ControlMode] = {"CWP": "software", "DIGITAL": "digital", "ANALOG": "analog"}


class ObisChannel(TypedDict):
    """A channel of a hub, for ObisLaser's conn argument."""

    hub: ObisHub
    channel: int


class ObisLaser(Laser):
    """An OBIS laser, with its power in mW. Pass a port name as conn, or {hub, channel}.

    :meth:`on` waits out the CDRH delay and the startup delay. The laser changes its control mode only while it is
    off, so a change while it is on turns it off, changes the mode, and turns it on again. It does not do mixed
    control."""

    unit: ClassVar[str] = "mW"

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
        self._range = Span(0.0, 0.0)
        self._enabled_at: float | None = None
        self._closed = False
        if isinstance(conn, str):
            self._hub: ObisHub | None = None
            self._channel: int | None = None
            self._address = ""
            self._link = ObisLink(conn, baud=baud)
        else:
            self._hub, self._channel = _parse_channel(conn)
            self._address = str(self._channel)
            self._link = self._hub.link
            self._hub.reserve(self._channel, uid)
        try:
            self._initialize()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                if self._hub is None:
                    self._link.close()
                raise ExceptionGroup("OBIS initialization and inhibition failed", [error, cleanup_error]) from None
            self._release_connection()
            raise
        self.log.info(f"Initialized OBIS: model={self._model}, max_power={self._range.high} mW")

    def _initialize(self) -> None:
        with self._link.transaction():
            reported = self._link.number(self._syst("INF:WAV?"))
            if abs(reported - self._wavelength) > _WAVELENGTH_MATCH_NM:
                raise ValueError(f"OBIS reports {reported} nm, but {self._wavelength} nm is configured")
            self._model = self._link.query(self._syst("INF:MOD?"))
            self._serial_number = self._link.query(self._syst("INF:SNUM?"))
            self.off()
            low = self._link.number(self._sour("POW:LIM:LOW?")) * 1000
            high = self._link.number(self._sour("POW:LIM:HIGH?")) * 1000
            if not 0 <= low < high:
                raise ObisError(f"Invalid OBIS power limits {low}..{high} mW")
            self._range = Span(low, high)
            self._write_control_mode("software")
            # Adopt the existing target within the firmware range and resolution.
            self._set_power(self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000)
            if self.autostart:
                self.log.warning("OBIS autostart is on: the laser emits at power-up")

    def _sour(self, command: str) -> str:
        return f"SOUR{self._address}:{command}"

    def _syst(self, command: str) -> str:
        return f"SYST{self._address}:{command}"

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        return self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        if self._closed or self._confirmed_off():
            return False
        return self._link.flag(self._sour("AM:STAT?"))

    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        reply = self._link.query(self._sour("AM:SOUR?"))
        if (mode := _MODE_REPLIES.get(reply.upper())) is None:
            raise ObisError(f"OBIS mode {reply!r} was set outside this driver")
        return mode

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="analog_in", direction="in", kind="analog"),
        ]

    def on(self) -> None:
        self._ensure_open()
        try:
            with self._link.transaction():
                if not self.is_on:
                    self._link.set_emission(self._address, True)
                    self._enabled_at = monotonic()
            # Wait outside the transaction so other channels on a hub stay available.
            self._wait_for_startup()
        except Exception as error:
            try:
                self.off()
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
        if not self.is_on:
            raise ObisError("OBIS emission permission was lost during startup")

    def off(self) -> None:
        if self._closed or self._confirmed_off():
            return
        self._link.set_emission(self._address, False)
        self._enabled_at = None

    # TODO: verify on real hardware the setpoint resolution; the wire format allows 0.01 mW (5 decimals in W).
    def _set_power(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("power must be finite")
        with self._link.transaction():
            self._link.command(self._sour(f"POW:LEV:IMM:AMPL {value / 1000:.5f}"))
            readback = self._link.number(self._sour("POW:LEV:IMM:AMPL?")) * 1000
            if abs(readback - value) > self._setpoint_tolerance_mw:
                raise ObisError(f"OBIS power setpoint reads {readback} mW after setting {value} mW")

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode not in _MODE_COMMANDS:
            raise ValueError(f"{self.uid} does not do {mode} control")
        with self._link.transaction():
            if self.control_mode == mode:
                return
            was_on = self.is_on
            if was_on:
                self.off()
            self._write_control_mode(mode)
        if was_on:
            self.on()

    def _write_control_mode(self, mode: ControlMode) -> None:
        self._link.command(self._sour(_MODE_COMMANDS[mode]))
        if self.control_mode != mode:
            raise ObisError(f"OBIS did not establish {mode} control")

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._link.number(self._sour("POW:LEV?")) * 1000

    @property
    @stream("slow", label="Base Plate Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._link.number(self._sour("TEMP:BAS?"), suffix="C")

    @property
    @fact(label="Model")
    def model(self) -> str:
        return self._model

    @property
    @fact(label="Serial Number")
    def serial_number(self) -> str:
        return self._serial_number

    @property
    @stream("slow", label="Operating Hours")
    def operating_hours(self) -> str:
        """Reply to SYST:HOUR?, unparsed until its format is confirmed."""
        self._ensure_open()
        return self._link.query(self._syst("HOUR?"))

    @property
    @stream("slow", label="CDRH Delay")
    def cdrh_delay(self) -> bool:
        """Whether emission starts 5 s after enable."""
        self._ensure_open()
        return self._link.flag(self._syst("CDRH?"))

    @property
    @stream("slow", label="Autostart")
    def autostart(self) -> bool:
        """Whether the laser emits at power-up."""
        self._ensure_open()
        return self._link.flag(self._syst("AUT?"))

    @property
    @stream(label="Interlock")
    def interlock(self) -> str:
        """Reply to SYST:LOCK?, unparsed until its meaning is confirmed."""
        # TODO: verify on real hardware what SYST:LOCK? replies with the interlock open and closed.
        self._ensure_open()
        return self._link.query(self._syst("LOCK?"))

    @property
    @stream("slow", label="Status Code")
    def status_code(self) -> str:
        """Hex status bits from SYST:STAT?."""
        self._ensure_open()
        return self._link.query(self._syst("STAT?"))

    @property
    @stream(label="Fault Code")
    def fault_code(self) -> str:
        """Hex fault bits from SYST:FAUL?; 00000000 means no fault."""
        # TODO: verify on real hardware what bit 31 (80000000) means; one lab saw it with no fault.
        self._ensure_open()
        return self._link.query(self._syst("FAUL?"))

    def dispose(self) -> None:
        """Turn the laser off, then close the port or release the channel; failures can be retried."""
        if self._closed:
            return
        self.off()
        self._release_connection()
        self._closed = True

    def _release_connection(self) -> None:
        if self._hub is None:
            self._link.close()
        elif self._channel is not None:
            self._hub.release(self._channel, self.uid)

    def _confirmed_off(self) -> bool:
        if self._hub is None or self._channel is None:
            return False
        return self._hub.confirmed_off(self._channel)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("OBIS laser is closed")


def _parse_channel(conn: Mapping[str, object]) -> tuple[ObisHub, int]:
    if set(conn) != {"hub", "channel"}:
        raise ValueError("conn must be a serial port name or {hub, channel}")
    hub, channel = conn["hub"], conn["channel"]
    if not isinstance(hub, ObisHub):
        raise ValueError(f"hub {hub!r} is not an ObisHub device")
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ValueError("channel must be an integer")
    return hub, channel

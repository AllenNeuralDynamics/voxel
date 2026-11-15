"""MPB Communications VFL laser (SHG variant) over serial; software control only."""

from enum import StrEnum
from math import isfinite
from time import monotonic, sleep
from typing import ClassVar

from rigup.device import action, fact, query, stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light.base import ControlMode
from vxl.devices.light.laser import Laser
from vxl_drivers.serial import SerialTransport

DEFAULT_BAUD = 9600
DEFAULT_MAX_POWER_MW = 500.0

_READY_PROMPT = "D >"
_FAULT_PROMPT = "F >"
_ERROR_MARKERS = ("MISSING_ARGUMENT", "DATA_CANNOT_BE_SET", "CAN_ONLY_BE_USED_FOR_TESTS")


class MpbCommandError(RuntimeError):
    """Raised when the MPB device reports a command error in its response."""


class Cmd(StrEnum):
    """Wire-format setters."""

    LD_ENABLE = "SETLDENABLE"
    POWER_ENABLE = "POWERENABLE"
    POWER_SETPOINT = "SETPOWER 0"
    SHG_TUNE = "SETSHGCMD"


class Query(StrEnum):
    """Wire-format getters."""

    MODEL = "GETMODEL"
    LD_ENABLE = "GETLDENABLE"
    POWER_ENABLE = "GETPOWERENABLE"
    POWER_SETPOINT = "GETPOWER 0"
    POWER = "POWER 0"
    POWER_LIMITS = "GETPOWERSETPTLIM 0"
    LD_CURRENT = "LDCURRENT 1"
    LD_TEMP = "LDTEMP 1"
    TEC_TEMP = "TECTEMP 1"
    SHG_TEMP_SETPOINT = "GETSHGTEMP"
    SHG_TEMP = "SHGTEMP"
    SHG_TUNE_INFO = "GETSHGTUNERDY"
    STATUS = "shlaser"


class MpbVflLaser(Laser):
    """One VFL per serial port, with its power in mW. :meth:`on` waits out the startup delay. It has no pins, so
    only commands control it."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        uid: str,
        port: str,
        wavelength: float,
        *,
        max_power_mw: float = DEFAULT_MAX_POWER_MW,
        startup_delay_s: float = 0.0,
        setpoint_tolerance_mw: float = 0.5,
        baud: int = DEFAULT_BAUD,
    ) -> None:
        super().__init__(uid=uid)
        if isinstance(wavelength, bool) or not isfinite(wavelength) or wavelength <= 0:
            raise ValueError("wavelength must be finite and positive in nm")
        if not isfinite(max_power_mw) or max_power_mw <= 0:
            raise ValueError("fallback maximum power must be finite and positive")
        if not isfinite(startup_delay_s) or startup_delay_s < 0:
            raise ValueError("startup delay must be finite and nonnegative")
        if not isfinite(setpoint_tolerance_mw) or setpoint_tolerance_mw <= 0:
            raise ValueError("setpoint tolerance must be finite and positive")
        self._wavelength = float(wavelength)
        self._range = Span(0.0, max_power_mw)
        self._startup_delay_s = startup_delay_s
        self._setpoint_tolerance_mw = setpoint_tolerance_mw
        self._enabled_at: float | None = None
        self._faulted = False
        self._closed = False
        self._t = SerialTransport(port, baud=baud)
        try:
            self._initialize()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("MPB initialization and inhibition failed", [error, cleanup_error]) from None
            finally:
                self._t.close()
            raise
        self.log.info(f"Initialized MPB VFL: port={port}, model={self._model}, max_power={self._range.high} mW")

    def _initialize(self) -> None:
        self._t.drain_input()
        self._model = self._query(Query.MODEL)
        self.off()
        self._set_control_mode("software")
        if self.control_mode != "software":
            raise MpbCommandError("MPB did not establish power control")
        self._range = self._read_power_limits(fallback=self._range)
        # Adopt the existing target within the firmware range and resolution.
        self._set_power(float(self._query(Query.POWER_SETPOINT)))

    def _read_power_limits(self, fallback: Span) -> Span:
        """Return firmware setpoint limits in mW; reply format "<min> <max>" per PYME."""
        try:
            minimum, maximum = (float(part) for part in self._query(Query.POWER_LIMITS).split()[:2])
        except (ValueError, MpbCommandError) as error:
            self.log.warning(f"Could not read power limits ({error!r}); using fallback {tuple(fallback)} mW")
            return fallback
        if not 0 <= minimum < maximum:
            self.log.warning(f"Invalid power limits {minimum}..{maximum} mW; using fallback {tuple(fallback)} mW")
            return fallback
        return Span(minimum, maximum)

    def _query(self, msg: str) -> str:
        """Send a command and return the trimmed response.

        Records whether the reply carries the fault (``F >``) prompt, then strips the
        ready (``D >``) and fault prompts from either end. Raises
        :class:`MpbCommandError` if the device responds with an error marker.
        """
        with self._t.transaction() as port:
            port.reset_input_buffer()
            port.write(f"{msg}\r".encode("ascii"))
            line = port.readline() or b""

        text = line.decode("ascii", errors="replace").strip()
        faulted = _FAULT_PROMPT in text
        if faulted and not self._faulted:
            self.log.warning(f"MPB reported a fault after {str(msg)!r}")
        self._faulted = faulted
        for prompt in (_READY_PROMPT, _FAULT_PROMPT):
            text = text.removeprefix(prompt).removesuffix(prompt).strip()
        for marker in _ERROR_MARKERS:
            if marker in text:
                raise MpbCommandError(f"Device rejected command {str(msg)!r}: {text}")
        return text

    def _flag(self, query: Query) -> bool:
        """Read a 0/1 reply; anything else, including no reply, is an error."""
        reply = self._query(query)
        if reply not in ("0", "1"):
            raise MpbCommandError(f"Expected 0 or 1 for {query.value!r}, got {reply!r}")
        return reply == "1"

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        return float(self._query(Query.POWER_SETPOINT))

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        return not self._closed and self._flag(Query.LD_ENABLE)

    @property
    def control_mode(self) -> ControlMode:
        self._ensure_open()
        if not self._flag(Query.POWER_ENABLE):  # 1 is APC (constant power), 0 is ACC
            raise MpbCommandError("MPB power control changed outside this driver")
        return "software"

    @property
    def pins(self) -> list[Pin]:
        return []

    def on(self) -> None:
        self._ensure_open()
        with self._t.transaction():
            try:
                self._enable()
            except Exception as error:
                try:
                    self.off()
                except Exception as cleanup_error:
                    raise ExceptionGroup("MPB enable and inhibition failed", [error, cleanup_error]) from None
                raise

    def _enable(self) -> None:
        if not self.is_on:
            self._query(f"{Cmd.LD_ENABLE} 1")
            self._enabled_at = monotonic()
            if not self.is_on:
                raise MpbCommandError("MPB did not report its laser diode enabled")
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_on:
            raise MpbCommandError("MPB enable permission was lost during startup")
        if self._faulted:
            raise MpbCommandError("MPB reports a fault")

    def off(self) -> None:
        if self._closed:
            return
        self._query(f"{Cmd.LD_ENABLE} 0")
        if self._flag(Query.LD_ENABLE):
            raise MpbCommandError("MPB did not disable its laser diode")
        self._enabled_at = None

    # TODO: verify on real hardware whether SETPOWER 0 accepts decimals; if so, change the write format.
    def _set_power(self, value: float) -> None:
        self._ensure_open()
        if not isfinite(value):
            raise ValueError("power must be finite")
        self._query(f"{Cmd.POWER_SETPOINT} {value:.0f}")
        readback = float(self._query(Query.POWER_SETPOINT))
        if abs(readback - value) > self._setpoint_tolerance_mw:
            raise MpbCommandError(f"MPB power setpoint reads {readback} mW after setting {value} mW")

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode != "software":
            raise ValueError(f"{self.uid} does only software control")
        self._query(f"{Cmd.POWER_ENABLE} 1")

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return float(self._query(Query.POWER))

    @property
    @stream("slow", label="Laser Diode Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return float(self._query(Query.LD_TEMP))

    @property
    @fact(label="Model")
    def model(self) -> str:
        """Identification string reported by the device at connection time."""
        return self._model

    @property
    @stream(label="Fault")
    def is_faulted(self) -> bool:
        """Whether the most recent reply carried the fault prompt."""
        return self._faulted

    @property
    @stream("slow", label="Diode Current", units="mA")
    def diode_current_ma(self) -> float:
        """Measured laser diode current."""
        self._ensure_open()
        return float(self._query(Query.LD_CURRENT))

    @property
    @stream("slow", label="TEC Temperature", units="°C")
    def tec_temperature_c(self) -> float:
        """Thermoelectric cooler temperature."""
        self._ensure_open()
        return float(self._query(Query.TEC_TEMP))

    @property
    @stream("slow", label="SHG Temperature", units="°C")
    def shg_temperature_c(self) -> float:
        """Measured SHG crystal temperature."""
        self._ensure_open()
        return float(self._query(Query.SHG_TEMP))

    @property
    @stream("slow", label="SHG Temperature Setpoint", units="°C")
    def shg_temperature_setpoint_c(self) -> float:
        """Commanded SHG crystal temperature; SHG tuning owns this value."""
        self._ensure_open()
        return float(self._query(Query.SHG_TEMP_SETPOINT))

    @query(label="SHG Tune Info")
    def shg_tune_info(self) -> dict[str, float | bool]:
        """Tuning readiness, hours of operation until the next tuning, and warm-up seconds left."""
        self._ensure_open()
        reply = self._query(Query.SHG_TUNE_INFO)
        parts = reply.split()
        if len(parts) < 3:
            raise MpbCommandError(f"Unexpected SHG tune info reply: {reply!r}")
        return {"ready": parts[0] == "1", "next_tuning_h": float(parts[1]), "warm_up_s": float(parts[2])}

    @action(label="Start SHG Tuning")
    def shg_tune_start(self) -> None:
        self._ensure_open()
        self._query(f"{Cmd.SHG_TUNE} 1")

    @action(label="Stop SHG Tuning")
    def shg_tune_stop(self) -> None:
        self._ensure_open()
        self._query(f"{Cmd.SHG_TUNE} 2")

    @query(label="Status")
    def status(self) -> list[str]:
        """Status report from `shlaser`, one entry per line."""
        self._ensure_open()
        return self._query(Query.STATUS).split("\r")

    def dispose(self) -> None:
        """Turn the laser off, then release the serial port; failures can be retried."""
        if self._closed:
            return
        self.off()
        self._t.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MPB laser is closed")

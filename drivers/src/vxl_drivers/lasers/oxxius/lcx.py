"""Oxxius LCX laser, and the combiner's modulator that is linked to its slot."""

from math import isclose, isfinite
from time import monotonic, sleep
from typing import ClassVar

from rigup.interface import stream
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light import ControlMode, Laser, Modulator
from vxl_drivers.lasers.oxxius.hub import Cmd, OxxiusCommunicationError, OxxiusHub, Query


class OxxiusLCXLaser(Laser):
    """The LCX laser of 1 combiner slot, with its power in mW. It is slow to start: :meth:`on` starts it and waits
    out the startup delay, and :meth:`off` stops it.

    With ``fixed_power_mw`` its power cannot change, and no power command is ever sent. It has no pins: the wires go
    to the slot's :class:`OxxiusLCXModulator`."""

    unit: ClassVar[str] = "mW"

    def __init__(
        self,
        device_id: str,
        hub: OxxiusHub,
        prefix: str,
        wavelength: float,
        *,
        max_power_mw: float,
        min_power_mw: float = 0.0,
        fixed_power_mw: float | None = None,
        startup_delay_s: float = 0.0,
    ) -> None:
        super().__init__(device_id=device_id)
        if not all(isfinite(v) for v in (wavelength, min_power_mw, max_power_mw, startup_delay_s)):
            raise ValueError("Wavelength, power limits, and startup delay must be finite")
        if wavelength <= 0 or not 0 <= min_power_mw <= max_power_mw or max_power_mw <= 0:
            raise ValueError("Invalid wavelength or power limits")
        if startup_delay_s < 0:
            raise ValueError("Startup delay must be nonnegative")
        if fixed_power_mw is not None and (
            not isfinite(fixed_power_mw) or not min_power_mw <= fixed_power_mw <= max_power_mw
        ):
            raise ValueError("Fixed power must lie within the power limits")
        self._hub = hub
        self._wavelength = wavelength
        self._fixed = fixed_power_mw
        low, high = (min_power_mw, max_power_mw) if fixed_power_mw is None else (fixed_power_mw, fixed_power_mw)
        self._range = Span(float(low), float(high))
        self._startup_delay_s = startup_delay_s
        self._enabled_at: float | None = None
        self._closed = False
        self._prefix = hub.reserve(prefix, device_id, family="LCX")
        # A failure here keeps the reservation: when the laser cannot be stopped, nothing else must reuse the slot.
        hub.disable(self._prefix)
        self.log.info(f"Initialized LCX {self._prefix}: {wavelength} nm")

    @property
    def wavelength(self) -> float:
        return self._wavelength

    @property
    def power(self) -> float:
        self._ensure_open()
        if self._fixed is not None:
            return self._fixed
        return self._hub.number(Query.POWER_SETPOINT, self._prefix)

    @property
    def power_range(self) -> Span:
        return self._range

    @property
    def is_on(self) -> bool:
        """Whether the laser is permitted to run: its temperature regulation, not the light at this instant."""
        return not self._closed and self._hub.is_enabled(self._prefix)

    @property
    def control_mode(self) -> ControlMode:
        return "software"

    @property
    def pins(self) -> list[Pin]:
        return []

    def on(self) -> None:
        self._ensure_open()
        try:
            with self._hub.transaction():
                if not self.is_on:
                    self._hub.enable(self._prefix)
                    self._enabled_at = monotonic()
            # Wait outside the transaction so the other slots stay available.
            self._wait_for_startup()
        except Exception as error:
            try:
                self.off()
            except Exception as cleanup_error:
                raise ExceptionGroup("LCX start and inhibition failed", [error, cleanup_error]) from None
            raise

    def _wait_for_startup(self) -> None:
        if self._enabled_at is None:
            self._enabled_at = monotonic()
        remaining = self._startup_delay_s - (monotonic() - self._enabled_at)
        if remaining > 0:
            sleep(remaining)
        if not self.is_on:
            raise OxxiusCommunicationError("LCX emission permission was lost during startup")

    def off(self) -> None:
        if not self._closed:
            self._hub.disable(self._prefix)
            self._enabled_at = None

    def _set_power(self, value: float) -> None:
        self._ensure_open()
        if self._fixed is not None:
            return
        target = round(value, 1)
        with self._hub.transaction():
            self._hub.command(Cmd.POWER, target, self._prefix)
            if not isclose(self._hub.number(Query.POWER_SETPOINT, self._prefix), target, rel_tol=0, abs_tol=0.051):
                raise OxxiusCommunicationError("LCX power setpoint readback differs")

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode != "software":
            raise ValueError(f"{self.id} does only software control")

    @property
    @stream("fast", label="Measured Power", units="mW")
    def measured_power_mw(self) -> float:
        self._ensure_open()
        return self._hub.number(Query.POWER, self._prefix)

    @property
    @stream("slow", label="Base Plate Temperature", units="°C")
    def temperature_c(self) -> float:
        self._ensure_open()
        return self._hub.number(Query.TEMPERATURE, self._prefix)

    def dispose(self) -> None:
        """Stop the laser and release its slot; the rig closes the hub."""
        if not self._closed:
            self.off()
            self._hub.release(self._prefix, self.id)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCX laser is closed")


class OxxiusLCXModulator(Modulator):
    """The combiner's modulator that is linked to 1 LCX slot: the part of the laser's light that leaves the slot.

    100 % is ``max_output_power_mw``, which must not be more than the laser gives. The combiner takes the level as a
    power in mW and has no switch for the modulator, so this keeps whether it is on, and its control mode. While it
    is off, its power is 0 and no wire can open it. In analog control a wire sets the level, and a power that is set
    is kept for the other modes. It does not do mixed control."""

    def __init__(self, device_id: str, hub: OxxiusHub, prefix: str, *, max_output_power_mw: float) -> None:
        super().__init__(device_id=device_id)
        if not isfinite(max_output_power_mw) or max_output_power_mw <= 0:
            raise ValueError("Output maximum must be finite and positive")
        self._hub = hub
        self._full_scale = max_output_power_mw
        self._level = 0.0
        self._mode: ControlMode = "software"
        self._on = False
        self._closed = False
        self._prefix = hub.reserve_modulator(prefix, device_id)
        try:
            self.off()
        except Exception:
            hub.release_modulator(self._prefix, device_id)
            raise

    @property
    def power(self) -> float:
        return self._level

    @property
    def power_range(self) -> Span:
        return Span(0.0, 100.0)

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def control_mode(self) -> ControlMode:
        return self._mode

    @property
    def pins(self) -> list[Pin]:
        return [
            Pin(name="ttl_in", direction="in", kind="digital"),
            Pin(name="analog_in", direction="in", kind="analog"),
        ]

    def on(self) -> None:
        self._ensure_open()
        if self._on:
            return
        with self._hub.transaction():
            self._write_level()
            self._hub.set_flag(Cmd.DIGITAL, Query.DIGITAL, self._mode == "digital", self._prefix)
            self._hub.set_flag(Cmd.ANALOG, Query.ANALOG, self._mode == "analog", self._prefix)
            self._on = True

    # TODO: verify on real hardware that a linked power of 0 blocks the light, and that TTL and AM can change while
    # the laser runs; the driver that this replaces stopped the laser for both.
    def off(self) -> None:
        if self._closed:
            return
        with self._hub.transaction():
            self._hub.set_flag(Cmd.DIGITAL, Query.DIGITAL, False, self._prefix)
            self._hub.set_flag(Cmd.ANALOG, Query.ANALOG, False, self._prefix)
            self._hub.set_linked_power(self._prefix, 0.0)
            self._on = False

    def _set_power(self, value: float) -> None:
        self._ensure_open()
        with self._hub.transaction():
            self._level = value
            if self._on and self._mode != "analog":
                self._write_level()

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        if mode == "mixed":
            raise ValueError(f"{self.id} does not do mixed control")
        if mode == self._mode:
            return
        with self._hub.transaction():
            was_on = self._on
            if was_on:
                self.off()
            self._mode = mode
            if was_on:
                self.on()

    def _write_level(self) -> None:
        """Send the level as a power in mW: the full scale in analog control, where a wire sets the level."""
        target = self._full_scale if self._mode == "analog" else self._full_scale * self._level / 100
        self._hub.set_linked_power(self._prefix, round(target, 1))

    def dispose(self) -> None:
        """Close the modulator and release it; the rig closes the hub."""
        if not self._closed:
            self.off()
            self._hub.release_modulator(self._prefix, self.id)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LCX modulator is closed")

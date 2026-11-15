"""One RF line of an MPDS, as a modulator."""

from typing import Any, Literal

from rigup.device import fact
from vxlib.vector import Span

from vxl.devices.base import Pin
from vxl.devices.light.base import ControlMode
from vxl.devices.light.modulator import Modulator
from vxl_drivers.modulators.mpds.hub import InputMode, MPDSHub
from vxl_drivers.modulators.mpds.settings import MPDSSettings


class MPDSModulator(Modulator):
    """One RF line of an MPDS: the part of 1 laser's light that the AOTF lets through, in %.

    ``settings`` gives the RF frequency, the RF power interval, and an optional calibration from RF power to
    optical %. With no calibration, the power is a linear scale of the RF power interval, not of the light.

    The line has 1 input, ``mod_in``, and the rig says how it is used. As ``digital``, a wire switches the line and
    :meth:`set_power` sets its level. As ``analog``, a wire sets the level: the RF power goes to its maximum, and a
    power that is set is kept for software control. The line changes its input only while it is off, so a change of
    the control mode while it is on turns it off, changes the mode, and turns it on again."""

    def __init__(
        self,
        uid: str,
        hub: MPDSHub,
        *,
        line: int,
        settings: MPDSSettings | dict[str, Any],
        mod_in: Literal["digital", "analog"] = "digital",
    ) -> None:
        super().__init__(uid=uid)
        if mod_in not in ("digital", "analog"):
            raise ValueError("mod_in must be digital or analog")
        self._settings = MPDSSettings.model_validate(settings)
        hub.validate_frequency(self._settings.frequency_mhz)
        hub.validate_power(self._settings.min_rf_power_dbm)
        hub.validate_power(self._settings.max_rf_power_dbm)
        self._hub = hub
        self._line = line
        self._pin = Pin(name="mod_in", direction="in", kind=mod_in)
        self._level = self._settings.minimum_level_percent
        self._mode: ControlMode = "software"
        self._closed = False
        with hub.transaction():
            hub.reserve_line(line, uid)
            try:
                hub.inhibit_line(line)
                hub.set_frequency(line, self._settings.frequency_mhz)
                hub.set_input_mode(line, InputMode.INTERNAL)
                hub.set_power(line, self._settings.rf_power(self._level))
            except Exception as error:
                # Keep the reservation when the line cannot be stopped: nothing else must reuse it.
                try:
                    hub.inhibit_line(line)
                except Exception as cleanup_error:
                    raise ExceptionGroup(
                        "MPDS line initialization and inhibition failed", [error, cleanup_error]
                    ) from None
                hub.release_line(line, uid)
                raise

    @property
    @fact(label="RF Line")
    def line(self) -> int:
        return self._line

    @property
    def power(self) -> float:
        return self._level

    @property
    def power_range(self) -> Span:
        return Span(self._settings.minimum_level_percent, 100.0)

    @property
    def is_on(self) -> bool:
        if self._closed:
            return False
        state = self._hub.get_line(self._line)
        return state.enabled or state.input_mode == InputMode.EXTERNAL

    @property
    def control_mode(self) -> ControlMode:
        """The mode that was set: the controller cannot tell a wire that switches from a wire that sets the level."""
        return self._mode

    @property
    def pins(self) -> list[Pin]:
        return [self._pin]

    def on(self) -> None:
        self._ensure_open()
        target = InputMode.INTERNAL if self._mode == "software" else InputMode.EXTERNAL
        with self._hub.transaction():
            state = self._hub.get_line(self._line)
            if state.input_mode != target:
                self._hub.inhibit_line(self._line)
                self._hub.set_input_mode(self._line, target)
            if target == InputMode.INTERNAL and not (state.input_mode == target and state.enabled):
                self._hub.set_enabled(self._line, True)

    def off(self) -> None:
        if not self._closed:
            self._hub.inhibit_line(self._line)

    def _set_power(self, value: float) -> None:
        self._ensure_open()
        with self._hub.transaction():
            if self._mode != "analog":
                self._hub.set_power(self._line, self._settings.rf_power(value))
            self._level = value

    def _set_control_mode(self, mode: ControlMode) -> None:
        self._ensure_open()
        with self._hub.transaction():
            if mode == self._mode:
                return
            was_on = self.is_on
            self._hub.inhibit_line(self._line)
            self._hub.set_power(self._line, self._settings.rf_power(100.0 if mode == "analog" else self._level))
            self._mode = mode
            if was_on:
                self.on()

    def dispose(self) -> None:
        """Turn the line off and release it; the rig closes the hub."""
        if self._closed:
            return
        self.off()
        self._hub.release_line(self._line, self.uid)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("MPDS line is closed")

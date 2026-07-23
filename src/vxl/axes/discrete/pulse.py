import time
from collections.abc import Mapping

from vxlib.quantity import VoltageRange

from vxl.daq.analog import AnalogOnDemandOutput

from .base import DiscreteAxis

_DEFAULT_PULSE_VOLTAGE = VoltageRange(min=0.0, max=5.0)
_PULSE_DURATION_S = 0.05


class PulseDiscreteAxis(DiscreteAxis):
    """Discrete axis that selects a slot by pulsing one output line per slot.

    The generator declares one port per slot, keyed by slot index
    (``{"0": ao6, "1": ao7}``). Moving to a slot drives that slot's line to the pulse
    voltage's ``max`` for ``_PULSE_DURATION_S`` while forcing every other line to
    ``min`` (rest), then returns all lines to rest — one atomic write per phase, so
    exactly one line is ever asserted. The wheel controller reads the pulse as a
    position select. Open-loop: position reflects the last commanded slot, not sensed
    feedback.

    The generator is an ``AnalogOnDemandOutput`` — the pulse is software-timed and claims
    no clock or trigger, so the axis can select a slot while a clocked acquisition
    owns the same card's AO timing only when the vendor permits the two tasks to use
    disjoint output resources. On NI 6738/6739 cards, the pulse channels must occupy
    different four-channel AO banks from the acquisition. Signal type lives in the
    generator, so this one axis serves analog on-demand today and digital on-demand
    later without a separate implementation.

    The axis owns its generator for its lifetime. ``halt`` returns every line to the
    rest level without releasing the generator; ``close`` resets it and releases its
    resources. Homes to slot 0 at construction so the position is commanded, never
    assumed.
    """

    def __init__(
        self,
        uid: str,
        *,
        generator: AnalogOnDemandOutput,
        slots: Mapping[int | str, str | None],
        slot_count: int | None = None,
        pulse_voltage: VoltageRange | None = None,
    ) -> None:
        """Initialize a pulse-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            generator: On-demand output with one port per slot, keyed by slot index.
            slots: Slot index to label, e.g. ``{0: "GFP", 1: "RFP"}``.
            slot_count: Total slots; inferred from ``slots`` when None.
            pulse_voltage: Select-pulse levels — ``max`` is the pulse peak, ``min`` the
                rest level. Defaults to 0-5 V.

        Raises:
            ValueError: If ``generator`` lacks a port for any slot index.
        """
        super().__init__(uid=uid, slots=slots, slot_count=slot_count)
        self._generator = generator
        self._pulse_voltage = pulse_voltage or _DEFAULT_PULSE_VOLTAGE

        available = set(generator.ports)
        missing = [i for i in range(self.slot_count) if str(i) not in available]
        if missing:
            raise ValueError(f"{generator.uid} has no port for slot(s) {missing}; ports: {sorted(available)}")

        self._position = 0
        self._is_moving = False
        self.move(0)

    @property
    def position(self) -> int:
        return self._position

    @property
    def is_moving(self) -> bool:
        return self._is_moving

    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        del wait, timeout  # the pulse is synchronous and fixed-duration; nothing to wait on
        if not (0 <= slot < self.slot_count):
            raise ValueError(f"Invalid slot {slot}; valid range is 0..{self.slot_count - 1}")

        peak = self._pulse_voltage.max
        rest = self._pulse_voltage.min
        rest_all = {str(i): rest for i in range(self.slot_count)}

        self._is_moving = True
        try:
            # One atomic write drives the selected line to the pulse peak and every
            # other line to rest, so exactly one line is ever asserted — even if a
            # prior pulse was interrupted mid-cycle and left its line high. A second
            # write returns all lines to rest.
            self._generator.set_voltages({**rest_all, str(slot): peak})
            time.sleep(_PULSE_DURATION_S)
            self._generator.set_voltages(rest_all)
            self._position = slot
        finally:
            self._is_moving = False

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        self.move(0, wait=wait, timeout=timeout)

    def halt(self) -> None:
        rest = self._pulse_voltage.min
        try:
            self._generator.set_voltages({str(i): rest for i in range(self.slot_count)})
        finally:
            self._is_moving = False

    def close(self) -> None:
        """Reset the owned generator and release its resources."""
        try:
            self._generator.reset()
        finally:
            self._is_moving = False

    def await_movement(self, timeout: float | None = None) -> None:
        start = time.time()
        while self._is_moving:
            if timeout is not None and (time.time() - start) > timeout:
                raise TimeoutError("Movement did not complete within timeout")
            time.sleep(0.01)

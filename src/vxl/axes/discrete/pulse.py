import time
from collections.abc import Mapping

from vxl.daq.analog import OnDemandAO
from vxl.daq.digital import OnDemandDO

from .base import DiscreteAxis

_DEFAULT_ACTIVE_VOLTAGE = 5.0
_DEFAULT_INACTIVE_VOLTAGE = 0.0
_PULSE_DURATION_S = 0.05


class PulseDiscreteAxis(DiscreteAxis):
    """Discrete axis that selects a slot by pulsing one output line per slot.

    The generator declares one output per slot, keyed by slot index
    (``{"0": ao6, "1": ao7}``). Moving to a slot drives that slot's line to the pulse
    active level for ``_PULSE_DURATION_S`` while forcing every other line to the
    inactive level, then returns all lines to inactive — one batch write per phase,
    so exactly one line is ever asserted. The wheel controller reads the pulse as a
    position select. Open-loop: position reflects the last commanded slot, not sensed
    feedback.

    The generator may be an ``OnDemandAO`` or ``OnDemandDO``. The pulse is
    software-timed and claims no clock or trigger. Analog levels default to 5 V
    active and 0 V inactive; digital levels default to ``True`` and ``False``.
    Vendor resource rules determine whether the on-demand task can coexist with
    clocked acquisition tasks on the same hardware.

    The axis owns its generator for its lifetime. ``halt`` returns every line to the
    rest level without releasing the generator; ``close`` resets it and releases its
    resources. Homes to slot 0 at construction so the position is commanded, never
    assumed.
    """

    def __init__(
        self,
        uid: str,
        *,
        generator: OnDemandAO | OnDemandDO,
        slots: Mapping[int | str, str | None],
        slot_count: int | None = None,
        active: bool | float | None = None,
        inactive: bool | float | None = None,
    ) -> None:
        """Initialize a pulse-driven discrete axis.

        Args:
            uid: Unique identifier for this device.
            generator: On-demand output with one channel per slot, keyed by slot index.
            slots: Slot index to label, e.g. ``{0: "GFP", 1: "RFP"}``.
            slot_count: Total slots; inferred from ``slots`` when None.
            active: Asserted output level. Defaults to 5 V for AO and ``True`` for DO.
            inactive: Resting output level. Defaults to 0 V for AO and ``False`` for DO.

        Raises:
            ValueError: If ``generator`` lacks a port for any slot index.
        """
        super().__init__(uid=uid, slots=slots, slot_count=slot_count)
        self._generator = generator
        if (active is None) != (inactive is None):
            raise ValueError("active and inactive must be provided together or both omitted")

        if isinstance(generator, OnDemandAO):
            resolved_active = _DEFAULT_ACTIVE_VOLTAGE if active is None else active
            resolved_inactive = _DEFAULT_INACTIVE_VOLTAGE if inactive is None else inactive
            if isinstance(resolved_active, bool) or not isinstance(resolved_active, (int, float)):
                raise TypeError("active must be a numeric voltage for an OnDemandAO generator")
            if isinstance(resolved_inactive, bool) or not isinstance(resolved_inactive, (int, float)):
                raise TypeError("inactive must be a numeric voltage for an OnDemandAO generator")
            self._active: bool | float = float(resolved_active)
            self._inactive: bool | float = float(resolved_inactive)
            voltage_range = generator.voltage_range
            for name, level in (("active", self._active), ("inactive", self._inactive)):
                if not voltage_range.min <= level <= voltage_range.max:
                    raise ValueError(
                        f"{name} voltage {level}V is outside generator range "
                        f"[{voltage_range.min}, {voltage_range.max}]V"
                    )
            available = set(generator.ports)
        elif isinstance(generator, OnDemandDO):
            resolved_active = True if active is None else active
            resolved_inactive = False if inactive is None else inactive
            if not isinstance(resolved_active, bool):
                raise TypeError("active must be bool for an OnDemandDO generator")
            if not isinstance(resolved_inactive, bool):
                raise TypeError("inactive must be bool for an OnDemandDO generator")
            self._active = resolved_active
            self._inactive = resolved_inactive
            available = set(generator.lines)
        else:
            raise TypeError(f"generator must be OnDemandAO or OnDemandDO, got {type(generator).__name__}")

        if self._active == self._inactive:
            raise ValueError("active and inactive must differ")

        missing = [i for i in range(self.slot_count) if str(i) not in available]
        if missing:
            raise ValueError(f"{generator.uid} has no output for slot(s) {missing}; outputs: {sorted(available)}")

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

        self._is_moving = True
        try:
            # One batch write drives the selected line active and every other line
            # inactive. A second write returns all lines to inactive.
            self._set_levels(slot)
            time.sleep(_PULSE_DURATION_S)
            self._set_levels(None)
            self._position = slot
        finally:
            self._is_moving = False

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        self.move(0, wait=wait, timeout=timeout)

    def halt(self) -> None:
        try:
            self._set_levels(None)
        finally:
            self._is_moving = False

    def _set_levels(self, active_slot: int | None) -> None:
        if isinstance(self._generator, OnDemandAO):
            levels = {str(i): float(self._inactive) for i in range(self.slot_count)}
            if active_slot is not None:
                levels[str(active_slot)] = float(self._active)
            self._generator.set_voltages(levels)
        else:
            states = {str(i): bool(self._inactive) for i in range(self.slot_count)}
            if active_slot is not None:
                states[str(active_slot)] = bool(self._active)
            self._generator.set_states(states)

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

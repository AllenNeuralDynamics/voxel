import math
import time
from collections.abc import Mapping

from vxl.devices.axes.discrete import DiscreteAxis
from vxl.devices.axes.discrete.base import DiscreteAxisState, SlotContent


class SimulatedDiscreteAxis(DiscreteAxis):
    def __init__(
        self,
        device_id: str,
        slots: Mapping[int | str, SlotContent],  # e.g. {0: "GFP", 1: "RFP", 2: "Cy5"}
        slot_count: int | None = None,
        start_pos: int = 0,
        settle_seconds: float = 0.05,
    ) -> None:
        super().__init__(device_id=device_id, slots=slots, slot_count=slot_count)

        if not (0 <= start_pos < self.slot_count):
            raise ValueError("start_pos out of range")

        self._settle = float(settle_seconds)
        if not math.isfinite(self._settle) or self._settle < 0:
            raise ValueError("settle_seconds must be finite and non-negative")
        self._state = self._state_at(start_pos, target=None, is_moving=False)
        self._settle_deadline: float | None = None
        self.log.debug(
            "SimulatedDiscreteAxis %s: Initialized at position %s with %s slots",
            device_id,
            start_pos,
            self.slot_count,
        )

    # --------- state ----------
    @property
    def state(self) -> DiscreteAxisState:
        if self._settle_deadline is not None and time.monotonic() >= self._settle_deadline:
            self._state = self._state_at(self._state.target, target=self._state.target, is_moving=False)
            self._settle_deadline = None
        return self._state

    # --------- commands ----------
    def move_to_slot(self, slot: int, *, wait: bool = False, timeout_s: float | None = None) -> None:
        if not (0 <= slot < self.slot_count):
            msg = f"Invalid slot {slot}; valid range is 0..{self.slot_count - 1}"
            raise ValueError(msg)

        if self.state.slot == slot or self._settle == 0:
            self._state = self._state_at(slot, target=slot, is_moving=False)
            self._settle_deadline = None
        else:
            self._state = self._state_at(None, target=slot, is_moving=True)
            self._settle_deadline = time.monotonic() + self._settle
        if wait:
            self.await_movement(timeout_s)

    def home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        self.log.debug("SimulatedDiscreteAxis %s: home() called - moving to slot 0", self.id)
        self.move_to_slot(0, wait=wait, timeout_s=timeout_s)

    def halt(self) -> None:
        """Halt motion, retaining the target and any resolved position."""
        state = self.state
        self._settle_deadline = None
        self._state = self._state_at(state.slot, target=state.target, is_moving=False)

    def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait for idle using a monotonic timeout in seconds."""
        deadline = time.monotonic() + timeout_s if timeout_s is not None else None
        while self.state.is_moving:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                raise TimeoutError("Movement did not complete within timeout")
            time.sleep(min(0.01, deadline - now) if deadline is not None else 0.01)

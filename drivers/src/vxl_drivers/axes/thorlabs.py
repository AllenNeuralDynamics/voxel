"""Thorlabs motorized flip mounts."""

from collections.abc import Mapping
from time import monotonic, sleep

from pylablib.devices.Thorlabs import MFF
from rigup.interface import integer, stream

from vxl.devices.axes.discrete.base import DiscreteAxis, DiscreteAxisState, SlotContent


class MFF101(DiscreteAxis):
    """Two-slot MFF101 controlled through pylablib's APT backend.

    ``conn`` is the device serial number or serial port. The mount has no
    calibration cycle or supported stop command; home selects slot zero.
    """

    def __init__(
        self,
        uid: str,
        *,
        conn: str,
        slots: Mapping[int | str, SlotContent] | None = None,
        flip_time_ms: int = 500,
    ) -> None:
        if any(int(index) not in (0, 1) for index in (slots or {})):
            raise ValueError("MFF101 slots must be 0 or 1")
        super().__init__(uid=uid, slots=slots or {}, slot_count=2)
        self._target: int | None = None
        self._inst = MFF(conn)
        try:
            self.flip_time_ms = flip_time_ms
        except Exception:
            self._inst.close()
            raise

    @property
    def state(self) -> DiscreteAxisState:
        position = self._inst.get_state()
        return DiscreteAxisState(position=position, target=self._target, is_moving=position is None)

    def move_to_slot(self, slot: int, *, wait: bool = False, timeout_s: float | None = None) -> None:
        if slot not in (0, 1):
            raise ValueError("MFF101 slots must be 0 or 1")
        self._inst.move_to_state(slot)
        self._target = slot
        if wait:
            self._await_slot(slot, timeout_s)

    def home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Return to slot zero."""
        self.move_to_slot(0, wait=wait, timeout_s=timeout_s)

    def halt(self) -> None:
        raise NotImplementedError("MFF101 does not support stopping a flip in progress")

    def await_movement(self, timeout_s: float | None = None) -> None:
        self._await_slot(None, timeout_s)

    def _await_slot(self, slot: int | None, timeout: float | None) -> None:
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            position = self._inst.get_state()
            if position is not None and (slot is None or position == slot):
                return
            if deadline is not None and monotonic() >= deadline:
                raise TimeoutError(f"MFF101 {self.uid} movement timed out")
            sleep(0.05)

    @integer(minimum=500, maximum=2800, step=100)
    @stream(label="Flip Time", units="ms", desc="Time to travel between slots.")
    def flip_time_ms(self) -> int:
        return round(self._inst.get_flipper_parameters().transit_time * 1000)

    @flip_time_ms.setter
    def flip_time_ms(self, value: int) -> None:
        self._inst.setup_flipper(transit_time=value / 1000)

    def dispose(self) -> None:
        self._inst.close()

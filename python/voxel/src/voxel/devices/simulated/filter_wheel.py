import threading
import time
from collections.abc import Mapping

from voxel.devices.interfaces.filter_wheel import VoxelFilterWheel


class SimulatedFilterWheel(VoxelFilterWheel):
    def __init__(
        self,
        uid: str,
        labels: Mapping[int, str | None],  # e.g. {1: "GFP", 2: "RFP", 3: None}
        slot_count: int | None = None,
        start_pos: int = 1,
        settle_seconds: float = 0.05,
    ) -> None:
        super().__init__(uid=uid)

        # --- normalize/validate labels & size ---
        max_idx = max(labels) if labels else 0
        self._slot_count = slot_count or max(max_idx, 0)
        if self._slot_count <= 0:
            raise ValueError('slot_count must be > 0')

        # Fill missing indices with None; enforce 1-based contiguous indices
        self._labels: dict[int, str | None] = {i: labels.get(i) for i in range(1, self._slot_count + 1)}

        if not (1 <= start_pos <= self._slot_count):
            raise ValueError('start_pos out of range')

        self._position = start_pos
        self._is_moving = False
        self._settle = float(settle_seconds)

    # --------- metadata ----------
    @property
    def slot_count(self) -> int:
        return self._slot_count

    @property
    def labels(self) -> Mapping[int, str | None]:
        return self._labels

    # --------- state ----------
    @property
    def position(self) -> int:
        return self._position

    @property
    def is_moving(self) -> bool:
        return self._is_moving

    # --------- commands ----------
    def move(self, slot: int, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        if not (1 <= slot <= self._slot_count):
            msg = f'Invalid slot {slot}; valid range is 1..{self._slot_count}'
            raise ValueError(msg)

        self._is_moving = True
        self._position = slot
        self.log.debug('SimulatedFilterWheel %s: Moving to slot %s (%s)', self.uid, slot, self._labels.get(slot))

        if wait:
            time.sleep(self._settle)
            self._is_moving = False
        else:
            # non-blocking path: schedule reset
            threading.Timer(self._settle, self._finish_move).start()

    def _finish_move(self) -> None:
        self._is_moving = False

    def home(self, *, wait: bool = True, timeout: float | None = 10.0) -> None:
        self.move(1, wait=wait, timeout=timeout)

    @property
    def label(self) -> str | None:
        return self._labels.get(self._position)

    def close(self) -> None:
        pass

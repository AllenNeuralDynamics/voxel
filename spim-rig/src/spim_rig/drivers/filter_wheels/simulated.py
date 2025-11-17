import threading
import time
from collections.abc import Mapping

from spim_rig.filter_wheel import FilterWheel


class SimulatedFilterWheel(FilterWheel):
    def __init__(
        self,
        uid: str,
        filters: Mapping[int | str, str | None],  # e.g. {0: "GFP", 1: "RFP", 2: "Cy5"}
        slot_count: int | None = None,
        start_pos: int = 0,
        settle_seconds: float = 0.05,
    ) -> None:
        super().__init__(uid=uid)

        # --- normalize/validate labels & size ---
        # Convert string keys to int (YAML might parse numeric keys as strings)
        normalized_filters: dict[int, str | None] = {int(k): v for k, v in filters.items()}

        max_idx = max(normalized_filters.keys()) if normalized_filters else -1
        self._slot_count = slot_count if slot_count is not None else (max_idx + 1)
        if self._slot_count <= 0:
            raise ValueError("slot_count must be > 0")

        # Fill missing indices with None; enforce 0-based contiguous indices
        self._labels: dict[int, str | None] = {i: normalized_filters.get(i) for i in range(self._slot_count)}

        if not (0 <= start_pos < self._slot_count):
            raise ValueError("start_pos out of range")

        self._position = start_pos
        self._is_moving = False
        self._settle = float(settle_seconds)
        self._timeout = 1.0

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
        self._timeout = timeout or 5.0
        if not (0 <= slot < self._slot_count):
            msg = f"Invalid slot {slot}; valid range is 0..{self._slot_count - 1}"
            raise ValueError(msg)

        self._is_moving = True
        self._position = slot
        self.log.debug("SimulatedFilterWheel %s: Moving to slot %s (%s)", self.uid, slot, self._labels.get(slot))

        if wait:
            time.sleep(self._settle)
            self._is_moving = False
        else:
            # non-blocking path: schedule reset
            threading.Timer(self._settle, self._finish_move).start()

    def _finish_move(self) -> None:
        self._is_moving = False

    def home(self, *, wait: bool = True, timeout: float | None = 10.0) -> None:
        self.move(0, wait=wait, timeout=timeout)

from abc import abstractmethod
from collections.abc import Mapping

from pydantic import BaseModel

from rigup import describe
from vxl.devices.axes.base import Axis
from vxl.devices.base import DeviceType


class DiscreteAxisState(BaseModel, frozen=True):
    """Discrete-axis feedback and command state.

    ``position`` is a feedback-resolved slot or ``None``. ``target`` retains the
    last successfully issued slot across arrival, halt, timeout, and external moves.
    Both indices are zero-based; an unset target is ``None``.
    """

    position: int | None
    target: int | None
    is_moving: bool


class DiscreteAxis(Axis):
    """Named discrete slots with synchronous motion commands and streamed state."""

    __DEVICE_TYPE__ = DeviceType.DISCRETE_AXIS

    def __init__(
        self,
        uid: str,
        slots: Mapping[int | str, str | None],
        slot_count: int | None = None,
    ) -> None:
        """Define zero-based slots, inferring slot count from the largest index when omitted.

        String keys are normalized to integers; missing labels remain ``None``.
        """
        super().__init__(uid=uid)

        # Normalize slots: convert string keys to int (YAML might parse numeric keys as strings)
        normalized_slots: dict[int, str | None] = {int(k): v for k, v in slots.items()}

        # Determine slot count
        max_idx = max(normalized_slots.keys()) if normalized_slots else -1
        self._slot_count = slot_count if slot_count is not None else (max_idx + 1)
        if self._slot_count <= 0:
            raise ValueError("slot_count must be > 0")

        # Fill missing indices with None; enforce 0-based contiguous indices
        self._labels: dict[int, str | None] = {i: normalized_slots.get(i) for i in range(self._slot_count)}

    # State properties _______________________________________________________________________________________________

    @property
    @describe(label="Slot Count", desc="Total number of physical slots.")
    def slot_count(self) -> int:
        """Physical slot count."""
        return self._slot_count

    @property
    @describe(label="Labels", desc="Map of slot index to human-readable label.")
    def labels(self) -> Mapping[int, str | None]:
        """Slot labels; ``None`` denotes an unlabeled slot."""
        return self._labels

    @property
    @abstractmethod
    @describe(label="State", desc="Current slot, last commanded slot, and movement status.", stream=True)
    def state(self) -> DiscreteAxisState:
        """Read a coherent snapshot; propagate communication errors."""

    # Motion commands ________________________________________________________________________________________________

    @abstractmethod
    @describe(label="Move", desc="Move to a slot by index.", stream=True)
    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        """Command a slot, optionally waiting for completion.

        ``timeout`` bounds the wait in seconds. Invalid slots raise ``ValueError``;
        an expired wait raises ``TimeoutError``.
        """

    @describe(label="Select", desc="Move to a slot by label.", stream=True)
    def select(self, label: str | None, *, wait: bool = False, timeout: float | None = None) -> None:
        """Command the first slot matching ``label``; ``None`` selects the first unlabeled slot.

        Missing labels raise ``KeyError``. Wait and timeout semantics match ``move``.
        """
        if label is None:
            # Choose first unlabeled slot
            for i in range(self._slot_count):
                if self._labels.get(i) is None:
                    return self.move(i, wait=wait, timeout=timeout)
            raise KeyError("No unlabeled slot available")
        # Choose first matching label
        for i in range(self._slot_count):
            if self._labels.get(i) == label:
                return self.move(i, wait=wait, timeout=timeout)
        raise KeyError(f"Label not found: {label!r}")

    @abstractmethod
    @describe(label="Home", desc="Home/calibrate the device.", stream=True)
    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        """Home the axis using the wait and timeout semantics of ``move``."""

    @abstractmethod
    @describe(label="Halt", desc="Emergency stop - halt all motion immediately.", stream=True)
    def halt(self) -> None:
        """Halt motion immediately."""

    @abstractmethod
    @describe(label="Await Movement", desc="Wait until the device stops moving.", stream=True)
    def await_movement(self, timeout: float | None = None) -> None:
        """Wait for idle; ``timeout`` is in seconds, with ``None`` unbounded.

        An expired wait raises ``TimeoutError``.
        """

    # Helper methods _________________________________________________________________________________________________

    def index_of(self, label: str) -> int:
        """Return the first slot matching ``label``; raise ``KeyError`` if absent."""
        for i in range(self._slot_count):
            if self._labels.get(i) == label:
                return i
        raise KeyError(label)

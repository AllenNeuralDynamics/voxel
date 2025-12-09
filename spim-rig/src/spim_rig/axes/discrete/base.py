from abc import abstractmethod
from collections.abc import Mapping

from pyrig import describe
from spim_rig.axes.base import SpimAxis
from spim_rig.device import DeviceType


class DiscreteAxis(SpimAxis):
    """Base class for discrete position devices.

    Provides interface for devices with a fixed set of positions,
    such as filter wheels, objective turrets, or dichroic sliders.
    Handles label-to-index mapping in the base class.
    """

    __DEVICE_TYPE__ = DeviceType.DISCRETE_AXIS

    def __init__(
        self,
        uid: str,
        slots: Mapping[int | str, str | None],
        slot_count: int | None = None,
    ) -> None:
        """Initialize a discrete axis device.

        Args:
            uid: Unique identifier for this device.
            slots: Mapping of slot index to label. Keys can be int or str (YAML compatibility).
                   e.g., {0: "GFP", 1: "RFP", 2: "Cy5", 3: None}
            slot_count: Total number of slots. If None, inferred from max slot index + 1.
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
        """Total number of available slots."""
        return self._slot_count

    @property
    @describe(label="Labels", desc="Map of slot index to human-readable label.")
    def labels(self) -> Mapping[int, str | None]:
        """Map of slot index to human-readable label (or None if unlabeled)."""
        return self._labels

    @property
    @abstractmethod
    @describe(label="Position", desc="Current slot index (0-indexed).", stream=True)
    def position(self) -> int:
        """Current slot index (0-based)."""

    @property
    @describe(label="Current Label", desc="Human-readable label of current position.", stream=True)
    def label(self) -> str | None:
        """Current slot label (derived from position)."""
        return self._labels.get(self.position)

    @property
    @abstractmethod
    @describe(label="Is Moving", desc="Whether the device is currently moving.", stream=True)
    def is_moving(self) -> bool:
        """Whether the device is currently moving."""

    # Motion commands ________________________________________________________________________________________________

    @abstractmethod
    @describe(label="Move", desc="Move to a slot by index.", stream=True)
    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        """Move to a slot by index.

        Args:
            slot: Target slot index (0-based).
            wait: If True, block until movement is complete.
            timeout: Maximum time to wait in seconds (only used if wait=True).

        Raises:
            ValueError: If an invalid slot is specified.
            TimeoutError: If wait is True and the move does not settle within timeout.
        """

    @describe(label="Select", desc="Move to a slot by label.", stream=True)
    def select(self, label: str | None, *, wait: bool = False, timeout: float | None = None) -> None:
        """Move to a slot by label.

        Args:
            label: Slot label/name. None moves to first unlabeled slot.
            wait: If True, block until movement is complete.
            timeout: Maximum time to wait in seconds (only used if wait=True).

        Raises:
            KeyError: If label not found.
            ValueError: If an invalid slot is specified.
            TimeoutError: If the move operation times out.
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
        """Home/calibrate the device.

        Args:
            wait: If True, block until movement is complete.
            timeout: Maximum time to wait in seconds (only used if wait=True).
        """

    @abstractmethod
    @describe(label="Halt", desc="Emergency stop - halt all motion immediately.", stream=True)
    def halt(self) -> None:
        """Emergency stop - halt all motion immediately."""

    @abstractmethod
    @describe(label="Await Movement", desc="Wait until the device stops moving.", stream=True)
    def await_movement(self, timeout: float | None = None) -> None:
        """Wait until the device stops moving.

        Args:
            timeout: Maximum time to wait in seconds. None means wait indefinitely.

        Raises:
            TimeoutError: If movement does not complete within timeout.
        """

    # Helper methods _________________________________________________________________________________________________

    def index_of(self, label: str) -> int:
        """Lookup label -> first matching slot index.

        Args:
            label: Slot label to find.

        Returns:
            Slot index for the label.

        Raises:
            KeyError: If the label is not found.
        """
        for i in range(self._slot_count):
            if self._labels.get(i) == label:
                return i
        raise KeyError(label)

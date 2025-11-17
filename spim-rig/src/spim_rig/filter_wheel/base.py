from abc import abstractmethod
from collections.abc import Mapping

from pyrig import Device, describe
from spim_rig.config import DeviceType


class FilterWheel(Device):
    """Driver abstraction for a discrete-position filter wheel.

    Conventions:
      - Slots are 0-indexed and contiguous: 0..slot_count-1.
      - Movement can block until settled when wait=True.
    """

    __DEVICE_TYPE__ = DeviceType.FILTER_WHEEL

    @property
    @abstractmethod
    @describe(label="Slot Count", desc="Total number of physical filter slots.")
    def slot_count(self) -> int:
        """Get the total number of physical slots."""

    @property
    @abstractmethod
    @describe(label="Filter Labels", desc="Map of slot index to human-readable label.")
    def labels(self) -> Mapping[int, str | None]:
        """Get the map of slot index to human label (or None if unlabeled)."""

    @property
    @abstractmethod
    @describe(label="Position", desc="Current slot index (0-indexed).")
    def position(self) -> int:
        """Get the current slot index (0..slot_count-1)."""

    @property
    @describe(label="Current Label", desc="Human-readable label of current position.")
    def label(self) -> str | None:
        """Get the current label derived from position."""
        return self.labels.get(self.position)

    @property
    @abstractmethod
    @describe(label="Is Moving", desc="Whether the wheel is currently in motion.")
    def is_moving(self) -> bool:
        """Check if the wheel is in motion/homing."""

    @abstractmethod
    def move(self, slot: int, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        """Move to slot index.

        Raises:
            ValueError: If an invalid slot is specified.
            TimeoutError: If wait is True and the move does not settle within the timeout period.
        """

    def select(self, label: str | None, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        """Move by label (or clear with None -> first unlabeled slot if defined).

        Raises:
            KeyError: If label not found.
            ValueError: If an invalid slot is specified.
            TimeoutError: If the move operation times out.
        """
        if label is None:
            # choose first unlabeled slot
            for i in range(self.slot_count):
                if self.labels.get(i) is None:
                    return self.move(i, wait=wait, timeout=timeout)
            raise KeyError("No unlabeled slot available")
        # choose first matching label (allow duplicates deterministically)
        for i in range(self.slot_count):
            if self.labels.get(i) == label:
                return self.move(i, wait=wait, timeout=timeout)
        error_msg = f"Label not found: {label!r}"
        raise KeyError(error_msg)

    @abstractmethod
    def home(self, *, wait: bool = True, timeout: float | None = 10.0) -> None:
        """Home/calibrate the wheel (optional; no-op if unsupported)."""

    def index_of(self, label: str) -> int:
        """Lookup label -> first matching slot index.

        Raises:
            KeyError: If the label is not found.
        """
        for i in range(self.slot_count):
            if self.labels.get(i) == label:
                return i
        raise KeyError(label)

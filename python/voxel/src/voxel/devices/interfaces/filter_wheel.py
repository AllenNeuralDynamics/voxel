from abc import abstractmethod
from collections.abc import Mapping

from voxel.devices.base import VoxelDevice, VoxelDeviceType


class VoxelFilterWheel(VoxelDevice):
    """
    Driver abstraction for a discrete-position filter wheel.

    Conventions:
      - Slots are 1-based and contiguous: 1..slot_count.
      - Movement can block until settled when wait=True.
    """

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid, device_type=VoxelDeviceType.FILTER_WHEEL)

    # --------- Static-ish metadata ----------
    @property
    @abstractmethod
    def slot_count(self) -> int:
        """Total number of physical slots."""

    @property
    @abstractmethod
    def labels(self) -> Mapping[int, str | None]:
        """
        Map slot index -> human label (or None if unlabeled).
        Length must equal slot_count.
        """

    # --------- State ----------
    @property
    @abstractmethod
    def position(self) -> int:
        """Current slot index (1..slot_count)."""

    @property
    def label(self) -> str | None:
        """Convenience: current label derived from position."""
        return self.labels.get(self.position)

    @property
    @abstractmethod
    def is_moving(self) -> bool:
        """True while the wheel is in motion/homing."""

    # --------- Commands ----------
    @abstractmethod
    def move(self, slot: int, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        """
        Move to slot index.
        Raises: ValueError (invalid slot), TimeoutError (if wait and not settled).
        """

    def select(self, label: str | None, *, wait: bool = True, timeout: float | None = 5.0) -> None:
        """
        Move by label (or clear with None -> first unlabeled slot if defined).
        Raises: KeyError if label not found, ValueError/TimeoutError as in `move`.
        """
        if label is None:
            # choose first unlabeled slot
            for i in range(1, self.slot_count + 1):
                if self.labels.get(i) is None:
                    return self.move(i, wait=wait, timeout=timeout)
            raise KeyError("No unlabeled slot available")
        # choose first matching label (allow duplicates deterministically)
        for i in range(1, self.slot_count + 1):
            if self.labels.get(i) == label:
                return self.move(i, wait=wait, timeout=timeout)
        raise KeyError(f"Label not found: {label!r}")

    @abstractmethod
    def home(self, *, wait: bool = True, timeout: float | None = 10.0) -> None:
        """Home/calibrate the wheel (optional; no-op if unsupported)."""

    # --------- Optional helpers ----------
    def index_of(self, label: str) -> int:
        """Lookup label -> first matching slot index."""
        for i in range(1, self.slot_count + 1):
            if self.labels.get(i) == label:
                return i
        raise KeyError(label)

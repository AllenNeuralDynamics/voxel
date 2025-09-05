from abc import ABC, abstractmethod

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.devices.linear_axis.base import LinearAxisDimension

from voxelstack.asi.ops.step_shoot import StepShootConfig


class TTLStepper(ABC):
    """An abstract capability for an axis that can be stepped by TTL pulses."""

    @abstractmethod
    def configure(self, cfg: StepShootConfig) -> None:
        """Configure the hardware for a step-and-shoot operation."""
        ...

    @abstractmethod
    def queue_absolute_move(self, position_mm: float) -> None:
        """Queue an absolute move to the ring buffer."""
        ...

    @abstractmethod
    def queue_relative_move(self, delta_mm: float) -> None:
        """Queue a relative move to the ring buffer."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Resets the step-and-shoot configuration and clears the buffer."""
        ...


class LinearAxis(VoxelDevice):
    def __init__(self, uid: str, dimension: LinearAxisDimension) -> None:
        super().__init__(uid=uid, device_type=VoxelDeviceType.LINEAR_AXIS)
        self._dimension = dimension

    @property
    def dimension(self) -> LinearAxisDimension:
        return self._dimension

    # --- motion ---
    @abstractmethod
    def move_abs(self, pos_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

    @abstractmethod
    def move_rel(self, delta_mm: float, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

    @abstractmethod
    def go_home(self, *, wait: bool = False, timeout_s: float | None = None) -> None: ...

    @abstractmethod
    def halt(self) -> None: ...

    @abstractmethod
    def await_movement(self, timeout_s: float | None = None) -> None: ...

    # -- state --
    @property
    @abstractmethod
    def position_mm(self) -> float: ...

    @property
    @abstractmethod
    def is_moving(self) -> bool: ...

    # -- Configuration ---
    @abstractmethod
    def set_zero_here(self) -> None: ...

    @abstractmethod
    def set_logical_position(self, pos_mm: float) -> None: ...

    @property
    @abstractmethod
    def upper_limit_mm(self) -> float: ...

    @upper_limit_mm.setter
    @abstractmethod
    def upper_limit_mm(self, mm: float) -> None: ...

    @property
    @abstractmethod
    def lower_limit_mm(self) -> float: ...

    @lower_limit_mm.setter
    @abstractmethod
    def lower_limit_mm(self, mm: float) -> None: ...

    @property
    def limits_mm(self) -> tuple[float, float]:
        return self.lower_limit_mm, self.upper_limit_mm

    @limits_mm.setter
    def limits_mm(self, limits: tuple[float, float]) -> None:
        self.lower_limit_mm = limits[0]
        self.upper_limit_mm = limits[1]

    @property
    @abstractmethod
    def speed_mm_s(self) -> float | None: ...

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, mm_per_s: float) -> None: ...

    @property
    @abstractmethod
    def acceleration_mm_s2(self) -> float | None: ...

    @acceleration_mm_s2.setter
    @abstractmethod
    def acceleration_mm_s2(self, mm_per_s2: float) -> None: ...

    @property
    @abstractmethod
    def backlash_mm(self) -> float | None: ...

    @backlash_mm.setter
    @abstractmethod
    def backlash_mm(self, mm: float) -> None: ...

    @property
    @abstractmethod
    def home(self) -> float | None: ...

    @home.setter
    @abstractmethod
    def home(self, pos_mm: float) -> None: ...

    # -- Capabilities --
    def get_ttl_stepper(self) -> TTLStepper | None:
        """
        Return a TTLStepper capability object if supported, otherwise None.
        This is an optional capability.
        """
        return None

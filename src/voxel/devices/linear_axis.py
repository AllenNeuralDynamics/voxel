from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from voxel.utils.descriptors.deliminated import deliminated_property

from .base import VoxelDevice, VoxelDeviceType


class LinearAxisDimension(StrEnum):
    X = "X"  # tiling axis
    Y = "Y"  # tiling axis
    Z = "Z"  # scanning axis
    N = "N"  # calibration axis, focusing axis


class ScanState(StrEnum):
    IDLE = "idle"
    CONFIGURED = "configured"
    SCANNING = "scanning"


@dataclass
class ScanConfig:
    class ScanType(StrEnum):
        STEP_AND_SHOOT = "step_and_shoot"
        CONTINUOUS = "continuous"

    start_mm: float
    stop_mm: float
    scan_type: ScanType
    step_size_um: float


class VoxelLinearAxis(VoxelDevice):
    """
    Base class for linear axis devices in Voxel
    :param name: Unique voxel ID within a Voxel Instrument
    :param dimension: LinearAxisDimension. X, Y, Z, or N
    """

    def __init__(self, name: str, dimension: LinearAxisDimension) -> None:
        super().__init__(device_type=VoxelDeviceType.LINEAR_AXIS, name=name)
        self.dimension: LinearAxisDimension = LinearAxisDimension(dimension)

    def __repr__(self) -> str:
        return (
            f"{self.name}, \n"
            f"dimension:        {self.dimension} \n"
            f"position_mm:      {self.position_mm}, \n"
            f"limits_mm:        {self.lower_limit_mm, self.upper_limit_mm}, \n"
            f"speed_mm_s:       {self.speed_mm_s}, \n"
            f"acceleration_ms:  {self.acceleration_ms}, \n"
            f"is_moving:        {self.is_moving}, \n"
        )

    @abstractmethod
    def configure_scan(self, config: ScanConfig) -> None:
        """
        Configure scanning parameters
        :param config: Scan configuration
        """

    @abstractmethod
    def start_scan(self) -> None:
        """Start scanning"""
        pass

    @abstractmethod
    def stop_scan(self) -> None:
        """Stop scanning"""
        pass

    @property
    @abstractmethod
    def scan_state(self) -> ScanState:
        """Get the current scan state"""
        pass

    @deliminated_property(unit="mm")
    @abstractmethod
    def position_mm(self) -> float:
        """Current position in mm"""
        pass

    @position_mm.setter
    @abstractmethod
    def position_mm(self, value: float) -> None:
        """Move to position in mm"""
        pass

    @property
    @abstractmethod
    def is_moving(self) -> bool:
        """Whether the axis is moving"""
        pass

    @abstractmethod
    def await_movement(self) -> None:
        """Wait until the axis stops moving"""
        pass

    @property
    @abstractmethod
    def upper_limit_mm(self) -> float:
        """Upper position limit in mm
        rtype:
        """
        pass

    @property
    @abstractmethod
    def lower_limit_mm(self) -> float:
        """Lower position limit in mm
        rtype: float
        """
        pass

    @abstractmethod
    def set_upper_limit_mm_in_place(self) -> None:
        """Set current position as the upper limit"""
        pass

    @abstractmethod
    def set_lower_limit_mm_in_place(self) -> None:
        """Set current position as the lower limit"""
        pass

    @abstractmethod
    def zero_in_place(self) -> None:
        """Set current position as zero"""
        pass

    # Other Kinematic properties and methods __________________________________________________________________________

    @property
    @abstractmethod
    def speed_mm_s(self) -> float:
        """Current speed in mm/s"""
        pass

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, value: float) -> None:
        """Set speed in mm/s"""
        pass

    @property
    @abstractmethod
    def acceleration_ms(self) -> float:
        """Current acceleration in m/s^2"""
        pass

    @acceleration_ms.setter
    @abstractmethod
    def acceleration_ms(self, value: float) -> None:
        """Set acceleration in m/s^2"""
        pass

    @abstractmethod
    def set_backlash_mm(self, value: float) -> None:
        """Set backlash in mm"""
        pass

    # Convenience methods ____________________________________________________________________________________________

    @abstractmethod
    def go_to_origin(self) -> None:
        """Move to origin"""
        pass

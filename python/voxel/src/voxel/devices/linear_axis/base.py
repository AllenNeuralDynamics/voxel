from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from voxel.devices.device import VoxelDevice, VoxelDeviceType
from voxel.utils.descriptors.deliminated import deliminated_float


class LinearAxisDimension(StrEnum):
    X = 'X'  # tiling axis
    Y = 'Y'  # tiling axis
    Z = 'Z'  # scanning axis
    N = 'N'  # calibration axis, focusing axis


class ScanState(StrEnum):
    IDLE = 'idle'
    CONFIGURED = 'configured'
    SCANNING = 'scanning'


@dataclass
class ScanConfig:
    class ScanType(StrEnum):
        """Type of scan to perform."""

        STEP_AND_SHOOT = 'step_and_shoot'
        CONTINUOUS = 'continuous'

    start_mm: float
    stop_mm: float
    scan_type: ScanType
    step_size_um: float

    def __repr__(self) -> str:
        return f'{self.scan_type} scan from {self.start_mm} to {self.stop_mm} in steps of {self.step_size_um} um'


class VoxelLinearAxis(VoxelDevice):
    """Base class for linear axis devices in Voxel.

    :param name: Unique voxel ID within a Voxel Instrument
    :param dimension: LinearAxisDimension. X, Y, Z, or N
    """

    def __init__(self, name: str, dimension: LinearAxisDimension) -> None:
        self.dimension: LinearAxisDimension = LinearAxisDimension(dimension)
        super().__init__(device_type=VoxelDeviceType.LINEAR_AXIS, uid=name)

    def __repr__(self) -> str:
        return (
            f'{self.uid}, \n'
            f'dimension:        {self.dimension} \n'
            f'position_mm:      {self.position_mm}, \n'
            f'limits_mm:        {self.lower_limit_mm, self.upper_limit_mm}, \n'
            f'speed_mm_s:       {self.speed_mm_s}, \n'
            f'acceleration_ms:  {self.acceleration_ms}, \n'
            f'is_moving:        {self.is_moving}, \n'
        )

    @abstractmethod
    def configure_scan(self, config: ScanConfig) -> None:
        """Configure scanning parameters.

        :param config: Scan configuration
        """

    @abstractmethod
    def start_scan(self) -> None:
        """Start scanning."""

    @abstractmethod
    def stop_scan(self) -> None:
        """Stop scanning."""

    @property
    @abstractmethod
    def scan_state(self) -> ScanState:
        """Get the current scan state."""

    @deliminated_float()
    @abstractmethod
    def position_mm(self) -> float:
        """Current position in mm."""

    @position_mm.setter
    @abstractmethod
    def position_mm(self, value: float) -> None:
        """Move to position in mm."""

    @property
    @abstractmethod
    def is_moving(self) -> bool:
        """Whether the axis is moving."""

    @abstractmethod
    def await_movement(self) -> None:
        """Wait until the axis stops moving."""

    @property
    @abstractmethod
    def upper_limit_mm(self) -> float:
        """Upper position limit in mm.

        :return: The upper limit in millimeters.
        :rtype: float
        """

    @property
    @abstractmethod
    def lower_limit_mm(self) -> float:
        """Lower position limit in mm.

        rtype: float
        """

    @abstractmethod
    def set_upper_limit_mm_in_place(self) -> None:
        """Set current position as the upper limit."""

    @abstractmethod
    def set_lower_limit_mm_in_place(self) -> None:
        """Set current position as the lower limit."""

    @abstractmethod
    def zero_in_place(self) -> None:
        """Set current position as zero."""

    # Other Kinematic properties and methods __________________________________________________________________________

    @property
    @abstractmethod
    def speed_mm_s(self) -> float:
        """Current speed in mm/s."""

    @speed_mm_s.setter
    @abstractmethod
    def speed_mm_s(self, value: float) -> None:
        """Set speed in mm/s."""

    @property
    @abstractmethod
    def acceleration_ms(self) -> float:
        """Current acceleration in m/s^2."""

    @acceleration_ms.setter
    @abstractmethod
    def acceleration_ms(self, value: float) -> None:
        """Set acceleration in m/s^2."""

    @abstractmethod
    def set_backlash_mm(self, value: float) -> None:
        """Set backlash in mm."""

    # Convenience methods ____________________________________________________________________________________________

    @abstractmethod
    def go_to_origin(self) -> None:
        """Move to origin."""

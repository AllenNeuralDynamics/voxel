from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.devices.linear_axis import VoxelLinearAxis, ScanState, ScanConfig, LinearAxisDimension


class SimulatedLinearAxis(VoxelLinearAxis):
    """Simulated Linear Axis implementation.
    :param name: Unique identifier for the device
    :param dimension: The dimension of the stage
    """

    def __init__(self, name: str, dimension: LinearAxisDimension):
        super().__init__(name, dimension)
        self._position_mm = 0.0
        self._speed_mm_s = 1.0
        self._acceleration_ms = 1.0
        self._lower_limit_mm = -10_000.0
        self._upper_limit_mm = 10_000.0

    def configure_scan(self, config: ScanConfig) -> None:
        self.log.info(f"Configuring scan: {config}")

    def start_scan(self) -> None:
        pass

    def stop_scan(self) -> None:
        pass

    @property
    def scan_state(self) -> ScanState:
        return ScanState.IDLE

    @deliminated_property(
        minimum=lambda self: self.lower_limit_mm,
        maximum=lambda self: self.upper_limit_mm,
        unit="mm",
        description="Current position in mm",
    )
    def position_mm(self) -> float | None:
        return self._position_mm

    @position_mm.setter
    def position_mm(self, value: float) -> None:
        self._position_mm = value

    @property
    def is_moving(self) -> bool:
        return False

    def await_movement(self) -> None:
        pass

    @property
    def upper_limit_mm(self) -> float:
        return self._upper_limit_mm

    @property
    def lower_limit_mm(self) -> float:
        return self._lower_limit_mm

    def set_upper_limit_mm_in_place(self) -> None:
        self._upper_limit_mm = self.position_mm

    def set_lower_limit_mm_in_place(self) -> None:
        self._lower_limit_mm = self.position_mm

    def zero_in_place(self) -> None:
        pass

    @property
    def speed_mm_s(self) -> float:
        return self._speed_mm_s

    @speed_mm_s.setter
    def speed_mm_s(self, value: float) -> None:
        self._speed_mm_s = value

    @property
    def acceleration_ms(self) -> float:
        return self._acceleration_ms

    @acceleration_ms.setter
    def acceleration_ms(self, value: float) -> None:
        self._acceleration_ms = value

    def set_backlash_mm(self, value: float) -> None:
        pass

    def go_to_origin(self) -> None:
        pass

    def close(self):
        pass

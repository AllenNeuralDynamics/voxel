import time

from tigerasi.tiger_controller import TigerController

from voxel.devices import VoxelDeviceError
from voxel.devices.filter_wheel import VoxelFilterWheel
from voxel.utils.descriptors.enumerated import enumerated_string

SWITCH_TIME_S = 0.1  # estimated timing


class ASIFilterWheel(VoxelFilterWheel):
    """Filter Wheel Abstraction from an ASI Tiger Controller."""

    def __init__(self, name: str, tigerbox: TigerController, wheel_id: str, filters: dict[str, int]):
        super().__init__(name=name)
        self.tigerbox = tigerbox
        self.wheel_id = wheel_id
        self._filters: dict[str, int] = filters
        self._current_filter: str = next(iter(filters))
        self._is_closed = False

    @property
    def filters(self) -> dict[str, int]:
        """Return a dictionary of filter names and their corresponding positions."""
        return self._filters

    def add_filter(self, filter_name: str, position: int):
        """Add a filter to the wheel."""
        if filter_name in self.filters:
            raise ValueError(f"Filter '{filter_name}' already exists on this wheel.")
        self.filters[filter_name] = position

    def set_filter(self, filter_name: str) -> None:
        """Set the filterwheel to the specified filter."""
        if self._is_closed:
            raise VoxelDeviceError("Filter wheel is closed and cannot be operated.")
        if filter_name not in self.filters:
            raise VoxelDeviceError(
                f"Attempted to set filter wheel {self.wheel_id} to {filter_name}\n"
                f"\tAvailable filters: {self.filters}"
            )
        if self._current_filter == filter_name:
            return  # Filter is already active, no need to change
        if self._current_filter:
            raise VoxelDeviceError(
                f"Unable to enable filter {filter_name} in filter wheel {self.wheel_id}\n"
                f"\tFilter {self._current_filter} is still active"
            )

        position = self.filters[filter_name]
        cmd_str = f"MP {position}\r\n"
        self.log.info(f"Setting filter to {filter_name}")
        self.tigerbox.send(f"FW {self.wheel_id}\r\n", read_until=f"\n\r{self.wheel_id}>")
        self.tigerbox.send(cmd_str, read_until=f"\n\r{self.wheel_id}>")
        time.sleep(SWITCH_TIME_S)
        self._current_filter = filter_name

    @enumerated_string(options=lambda self: self.filters.keys())
    def current_filter(self) -> str:
        """Return the name of the currently active filter, or None if no filter is active."""
        return self._current_filter

    def close(self):
        pass

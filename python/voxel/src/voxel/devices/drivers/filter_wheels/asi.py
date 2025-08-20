import time

from tigerasi.tiger_controller import TigerController

from voxel.devices import VoxelDeviceError
from voxel.devices.interfaces.filter_wheel import VoxelFilterWheel
from voxel.utils.descriptors.enumerated import enumerated_string

SWITCH_TIME_S = 0.1  # estimated timing


class ASIFilterWheel(VoxelFilterWheel):
    """Filter Wheel Abstraction from an ASI Tiger Controller."""

    def __init__(self, name: str, tigerbox: TigerController, wheel_id: str, filters: dict[int, str]):
        super().__init__(uid=name)
        self.tigerbox = tigerbox
        self.wheel_id = wheel_id
        self._filters: dict[int, str] = filters
        self._current_filter: int = next(iter(filters))
        self._is_closed = False

    @property
    def filters(self) -> dict[int, str]:
        """Return a dictionary of filter names and their corresponding positions."""
        return self._filters

    @enumerated_string(options=lambda self: self.filters.keys())
    def active_filter(self) -> str:
        """Return the name of the currently active filter, or None if no filter is active."""
        return self._filters.get(self._current_filter, "Error")

    @active_filter.setter
    def active_filter(self, filter_name: str) -> None:
        """Set the current filter to the specified filter name."""
        if self._is_closed:
            raise VoxelDeviceError("Filter wheel is closed and cannot be operated.")
        # Find the position of the filter
        position = next((pos for pos, name in self.filters.items() if name == filter_name), None)
        if position is None:
            raise VoxelDeviceError(f"Filter '{filter_name}' not found in the filter wheel.")

        if self._current_filter == position:
            return  # Filter is already active, no need to change

        self._send_set_filter_cmd(position)

    def _send_set_filter_cmd(self, position: int) -> None:
        """Set the filterwheel to the specified filter."""
        cmd_str = f"MP {self.filters[position]}\r\n"
        self._log.info(f"Setting filter to {self._filters[position]} (position {position})")
        self.tigerbox.send(f"FW {self.wheel_id}\r\n", read_until=f"\n\r{self.wheel_id}>")
        self.tigerbox.send(cmd_str, read_until=f"\n\r{self.wheel_id}>")
        time.sleep(SWITCH_TIME_S)
        self._current_filter = position

    def close(self):
        pass

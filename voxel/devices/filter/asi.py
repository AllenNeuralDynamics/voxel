import time
from typing import Dict, Optional
from tigerasi.tiger_controller import TigerController
from voxel.devices.filter import BaseFilter, BaseFilterWheel, VoxelFilterError

SWITCH_TIME_S = 0.1  # estimated timing


class ASIFilterWheel(BaseFilterWheel):
    """Filter Wheel Abstraction from an ASI Tiger Controller."""

    def __init__(self, id: str, tigerbox: TigerController, wheel_id: str):
        super().__init__(id)
        self.tigerbox = tigerbox
        self.wheel_id = wheel_id
        self.filters: Dict[str, int] = {}
        self._current_filter: Optional[str] = None
        self._is_closed = False

    def add_filter(self, name: str, position: int):
        """Add a filter to the wheel."""
        if name in self.filters:
            raise ValueError(f"Filter '{name}' already exists on this wheel.")
        self.filters[name] = position

    def set_filter(self, filter_name: str) -> None:
        """Set the filterwheel to the specified filter."""
        if self._is_closed:
            raise VoxelFilterError("Filter wheel is closed and cannot be operated.")
        if filter_name not in self.filters:
            raise VoxelFilterError(
                f"Attempted to set filter wheel {self.wheel_id} to {filter_name}\n"
                f"\tAvailable filters: {self.filters}"
            )
        if self._current_filter == filter_name:
            return  # Filter is already active, no need to change
        if self._current_filter:
            raise VoxelFilterError(
                f"Unable to enable filter {filter_name} in filter wheel {self.wheel_id}\n"
                f"\tFilter {self._current_filter} is still active"
            )

        position = self.filters[filter_name]
        cmd_str = f"MP {position}\r\n"
        self.log.info(f"Setting filter to {filter_name}")
        self.tigerbox.send(
            f"FW {self.wheel_id}\r\n", read_until=f"\n\r{self.wheel_id}>"
        )
        self.tigerbox.send(cmd_str, read_until=f"\n\r{self.wheel_id}>")
        time.sleep(SWITCH_TIME_S)
        self._current_filter = filter_name

    @property
    def current_filter(self) -> Optional[str]:
        """Return the name of the currently active filter, or None if no filter is active."""
        return self._current_filter

    def close(self):
        if not self._is_closed:
            self._current_filter = None
            if self.tigerbox.ser:
                self.tigerbox.ser.close()
            self._is_closed = True


class ASIFilter(BaseFilter):
    def __init__(self, id: str, name: str, wheel: ASIFilterWheel, position: int):
        super().__init__(id)
        self.name = name
        self.wheel = wheel
        self.position = position
        self.wheel.add_filter(name, position)

    def enable(self) -> None:
        """Enable this filter if no other filter is enabled"""
        self.wheel.set_filter(self.name)

    def disable(self) -> None:
        """Disable this filter if it's active."""
        if self.enabled:
            self.wheel._current_filter = None

    @property
    def enabled(self) -> bool:
        """Check if this filter is currently active."""
        return self.wheel.current_filter == self.name

    def close(self):
        self.wheel.close()

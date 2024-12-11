import time

from voxel.devices import VoxelDeviceError
from voxel.devices.filter import VoxelFilter, VoxelFilterWheel

SWITCH_TIME_S = 0.1  # simulated switching time


class SimulatedFilterWheel(VoxelFilterWheel):
    """Simulated Filter Wheel for testing without hardware."""

    def __init__(self, name: str, wheel_id: str):
        super().__init__(name)
        self.wheel_id = wheel_id
        self.filters: dict[str, int] = {}
        self._current_filter: str | None = None
        self._is_closed = False
        self.log.debug(f"Simulated Filter Wheel '{name}' initialized")

    def add_filter(self, filter_name: str, position: int):
        """Add a filter to the wheel."""
        if filter_name in self.filters:
            raise ValueError(f"Filter '{filter_name}' already exists on this wheel.")
        self.filters[filter_name] = position
        self.log.debug(f"Added filter '{filter_name}' at position {position}")

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
            self.log.warning(f"Attempting to enable filter: '{filter_name}' but it is already active")
            return
        if self._current_filter:
            raise VoxelDeviceError(
                f"Unable to enable filter {filter_name} in filter wheel {self.wheel_id}\n"
                f"\tFilter {self._current_filter} is still active"
            )

        time.sleep(SWITCH_TIME_S)  # Simulate switching time
        self._current_filter = filter_name
        self.log.debug(f"Filter set to '{filter_name}'")

    @property
    def current_filter(self) -> str | None:
        """Return the name of the currently active filter, or None if no filter is active."""
        return self._current_filter

    def close(self):
        if not self._is_closed:
            self._current_filter = None
            self._is_closed = True
            self.log.debug("Simulated Filter Wheel closed")


class SimulatedFilter(VoxelFilter):
    def __init__(self, name: str, wheel: SimulatedFilterWheel, position: int):
        super().__init__(name)
        self.wheel = wheel
        self.position = position
        self.wheel.add_filter(self.name, position)
        self.log.debug(f"Simulated Filter '{name}' initialized")

    def enable(self) -> None:
        """Enable this filter if no other filter is enabled"""
        self.wheel.set_filter(self.name)

    def disable(self) -> None:
        """Disable this filter if it's active."""
        if self.enabled:
            self.log.debug(f"Disabling filter '{self.name}'")
            self.wheel._current_filter = None

    @property
    def enabled(self) -> bool:
        """Check if this filter is currently active."""
        return self.wheel.current_filter == self.name

    def close(self):
        self.wheel.close()

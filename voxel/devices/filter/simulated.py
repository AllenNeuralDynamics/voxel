import time
from typing import Dict, Optional
from voxel.devices.filter import BaseFilter, BaseFilterWheel, VoxelFilterError

SWITCH_TIME_S = 0.1  # simulated switching time


class SimulatedFilterWheel(BaseFilterWheel):
    """Simulated Filter Wheel for testing without hardware."""

    def __init__(self, id: str, wheel_id: str):
        super().__init__(id)
        self.wheel_id = wheel_id
        self.filters: Dict[str, int] = {}
        self._current_filter: Optional[str] = None
        self._is_closed = False
        self.log.info(f"Simulated Filter Wheel '{id}' initialized")

    def add_filter(self, name: str, position: int):
        """Add a filter to the wheel."""
        if name in self.filters:
            raise ValueError(f"Filter '{name}' already exists on this wheel.")
        self.filters[name] = position
        self.log.info(f"Added filter '{name}' at position {position}")

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
            self.log.info(f"Filter '{filter_name}' is already active")
            return
        if self._current_filter:
            raise VoxelFilterError(
                f"Unable to enable filter {filter_name} in filter wheel {self.wheel_id}\n"
                f"\tFilter {self._current_filter} is still active"
            )

        self.log.info(f"Setting filter to '{filter_name}'")
        time.sleep(SWITCH_TIME_S)  # Simulate switching time
        self._current_filter = filter_name
        self.log.info(f"Filter set to '{filter_name}'")

    @property
    def current_filter(self) -> Optional[str]:
        """Return the name of the currently active filter, or None if no filter is active."""
        return self._current_filter

    def close(self):
        if not self._is_closed:
            self._current_filter = None
            self._is_closed = True
            self.log.info("Simulated Filter Wheel closed")


class SimulatedFilter(BaseFilter):
    def __init__(self, id: str, name: str, wheel: SimulatedFilterWheel, position: int):
        super().__init__(id)
        self.name = name
        self.wheel = wheel
        self.position = position
        self.wheel.add_filter(name, position)
        self.log.info(f"Simulated Filter '{id}' initialized")

    def enable(self) -> None:
        """Enable this filter if no other filter is enabled"""
        self.wheel.set_filter(self.name)

    def disable(self) -> None:
        """Disable this filter if it's active."""
        if self.enabled:
            self.log.info(f"Disabling filter '{self.name}'")
            self.wheel._current_filter = None

    @property
    def enabled(self) -> bool:
        """Check if this filter is currently active."""
        return self.wheel.current_filter == self.name

    def close(self):
        self.wheel.close()


# Usage example
if __name__ == "__main__":
    import logging

    def setup_simulated_filter_system():
        wheel = SimulatedFilterWheel("main_wheel", "simulated_wheel_id")

        red_filter = SimulatedFilter("red_filter", "red", wheel, 0)
        green_filter = SimulatedFilter("green_filter", "green", wheel, 1)
        blue_filter = SimulatedFilter("blue_filter", "blue", wheel, 2)

        return red_filter, green_filter, blue_filter, wheel

    def print_active_filter(wheel: SimulatedFilterWheel):
        wheel.log.info(f"Active filter: {wheel.current_filter or 'None'}")

    logging.basicConfig(level=logging.INFO)

    red, green, blue, wheel = setup_simulated_filter_system()
    print_active_filter(wheel)

    red.enable()
    print_active_filter(wheel)
    red.disable()

    green.enable()
    print_active_filter(wheel)
    green.disable()

    red.disable()
    print_active_filter(wheel)

    blue.enable()
    print_active_filter(wheel)

    blue.close()
    print_active_filter(wheel)

    try:
        red.enable()
    except VoxelFilterError as e:
        print(e)
    print_active_filter(wheel)

    try:
        red.close()
    except VoxelFilterError as e:
        print(e)
    print_active_filter(wheel)

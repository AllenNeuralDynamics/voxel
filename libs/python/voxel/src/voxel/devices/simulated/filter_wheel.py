from voxel.devices.interfaces.filter_wheel import VoxelFilterWheel
from voxel.utils.descriptors.enumerated import enumerated_string


class SimulatedFilterWheel(VoxelFilterWheel):
    def __init__(self, name: str, filters: dict[int, str]) -> None:
        super().__init__(name=name)
        self._filters = filters
        self._current_filter = self._filters[0] if filters else "None"

    @property
    def filters(self) -> dict[int, str]:
        """Return a dictionary of filter names and their corresponding positions."""
        return self._filters

    @enumerated_string(options=lambda self: self._filters.values())
    def current_filter(self) -> str:
        return self._current_filter

    @current_filter.setter
    def current_filter(self, filter_name: str) -> None:
        if filter_name in self._filters:
            self._current_filter = filter_name
        else:
            raise ValueError(f"Filter '{filter_name}' not found in the filter wheel.")

    def close(self) -> None:
        """Simulated close method."""
        self._log.info("Closed.")
        self._current_filter = "None"

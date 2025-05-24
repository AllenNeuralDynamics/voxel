from voxel.devices.filter_wheel import VoxelFilterWheel
from voxel.utils.descriptors.enumerated import enumerated_string


class SimulatedFilterWheel(VoxelFilterWheel):
    def __init__(self, name: str, filters: list[str]) -> None:
        super().__init__(name=name)
        self._filters = filters
        self._current_filter = self._filters[0] if filters else "None"

    @property
    def filters(self) -> dict[str, int]:
        """Return a dictionary of filter names and their corresponding positions."""
        return {filter_name: idx for idx, filter_name in enumerate(self._filters)}

    @enumerated_string(options=lambda self: self._filters)
    def current_filter(self) -> str:
        return self._current_filter

    @current_filter.setter
    def current_filter(self, filter_name: str) -> None:
        if filter_name in self._filters:
            self._current_filter = filter_name
        else:
            raise ValueError(f"Filter '{filter_name}' not found in the filter wheel.")

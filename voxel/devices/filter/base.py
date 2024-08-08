from abc import abstractmethod
from typing import Optional

from voxel.devices import VoxelDevice


class VoxelFilterError(Exception):
    """Custom """
    pass


class BaseFilter(VoxelDevice):
    """Base class for all voxel compliant filters
    Filters are typically part of a filter wheel. The wheel is responsible for moving the filter into the beam path.  \n
    The filter wheel tracks the current filter in use. It will not allow two filters to be enabled at the same time.
    The user must disable the current filter before enabling a new one.  \n
    # TODO: Determine the best behavior for enabling a filter while another is enabled. Simplest way is to just disable
        the current filter.
    """

    @abstractmethod
    def enable(self) -> None:
        """Enable the filter
        """
        pass

    @abstractmethod
    def disable(self) -> None:
        """Disable the filter
        """
        pass

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Check if the filter is currently enabled
        """
        pass


class BaseFilterWheel(VoxelDevice):

    @abstractmethod
    def add_filter(self, name: str, position: int):
        """Add a filter to the wheel."""
        pass

    @abstractmethod
    def set_filter(self, filter_name: str) -> None:
        """Set the filterwheel to the specified filter."""
        pass

    @property
    @abstractmethod
    def current_filter(self) -> Optional[str]:
        """Return the name of the currently active filter, or None if no filter is active."""
        pass

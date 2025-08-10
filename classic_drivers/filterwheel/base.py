from abc import abstractmethod

from ..base import VoxelDevice


class BaseFilterWheel(VoxelDevice):
    """
    Base class for filter wheel devices.
    """

    def __init__(self) -> None:
        """
        Initialize the BaseFilterWheel object.
        """
        self.filter_list: list = []

    @property
    def filters(self) -> dict[str, int]:
        """
        Get the list of filters in the filter wheel.

        :return: Dictionary of filter names and their positions
        :rtype: dict[str, int]
        """
        return {filter_name: i for i, filter_name in enumerate(self.filter_list)}

    @property
    @abstractmethod
    def filter(self) -> str:
        """
        Get the current filter.

        :return: Current filter name
        :rtype: str
        """
        pass

    @filter.setter
    @abstractmethod
    def filter(self, filter_name: str) -> None:
        """
        Set the current filter.

        :param filter_name: Filter name
        :type filter_name: str
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the filter wheel device.
        """
        pass

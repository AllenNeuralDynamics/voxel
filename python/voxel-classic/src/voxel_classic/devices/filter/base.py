from abc import abstractmethod

from voxel_classic.devices.base import BaseDevice


class BaseFilter(BaseDevice):
    """
    Base class for filter devices.
    """

    def __init__(self, uid: str) -> None:
        super().__init__(uid)

    @abstractmethod
    def enable(self) -> None:
        """
        Enable the filter device.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the filter device.
        """
        pass

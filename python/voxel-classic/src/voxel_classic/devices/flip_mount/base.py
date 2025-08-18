from abc import abstractmethod

from voxel_classic.devices.base import BaseDevice


class BaseFlipMount(BaseDevice):
    """
    Base class for flip mount devices.
    """

    def __init__(self, id: str) -> None:
        """
        Initialize the BaseFlipMount object.

        :param id: Flip mount ID
        :type id: str
        """
        super().__init__(id)

    @property
    @abstractmethod
    def position(self) -> str | None:
        """
        Get the position of the flip mount.

        :return: Position of the flip mount
        :rtype: str | None
        """
        pass

    @position.setter
    @abstractmethod
    def position(self, position_name: str) -> None:
        """
        Set the flip mount to a specific position.

        :param position_name: Position name
        :type position_name: str
        :param wait: Whether to wait for the flip mount to finish moving, defaults to False
        :type wait: bool, optional
        """
        pass

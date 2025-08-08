from abc import abstractmethod
from typing import List, Dict

from voxel_classic.devices.base import VoxelDevice


class BaseJoystick(VoxelDevice):
    """
    Base class for joystick devices.
    """

    @abstractmethod
    def stage_axes(self) -> List[str]:
        """
        Get the stage axes controlled by the joystick.

        :return: List of stage axes
        :rtype: list
        """
        pass

    @abstractmethod
    def joystick_mapping(self) -> Dict[str, str]:
        """
        Get the joystick mapping.

        :return: Joystick mapping
        :rtype: dict
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the joystick device.
        """
        pass

import time
import logging
from typing import Dict, Optional

from voxel.devices.controller.asi.tiger import TigerController

from voxel.devices.flip_mount.base import BaseFlipMount

STEPS_PER_UM = 10

POSITIONS = dict()


class TigerFlipMount(BaseFlipMount):
    """
    ThorlabsFlipMount class for handling Thorlabs flip mount devices.
    """

    def __init__(self, axis: str, tigerbox: TigerController, positions: Dict[str, int]) -> None:
        """
        Initialize the ThorlabsFlipMount object.

        :param axis: Tiger axis
        :type axis: str
        :param tigerbox: TigerController object, defaults to None
        :type tigerbox: Optional[TigerController], optional
        :param positions: Dictionary of positions
        :type positions: dict
        :raises ValueError: If an invalid position is provided
        """
        self.id = f"tiger flip mount: axis = {axis}"
        self.axis = axis.upper()
        super().__init__(id)
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.tigerbox = tigerbox
        for key, value in positions.items():
            POSITIONS[key] = value
        # default to starting in first position
        self._position = self.tigerbox.get_position_mm()[self.axis.upper()]

    @property
    def position(self) -> Optional[str]:
        """
        Get the current position of the flip mount.
        :return: Current position of the flip mount
        :rtype: str | None
        """
        position = self._position
        return next((key for key, value in POSITIONS.items() if value == position), "Unknown")

    @position.setter
    def position(self, position_name: str) -> None:
        """
        Set the flip mount to a specific position.

        :param position_name: Position name
        :type position_name: str
        """
        if position_name not in POSITIONS:
            raise ValueError(f"Invalid position {position_name}. Valid positions are {list(POSITIONS.keys())}")
        self._position = POSITIONS[position_name]
        self.tigerbox.move_absolute(**{self.axis: POSITIONS[position_name]})
        end_position = POSITIONS[position_name]
        while abs(self.tigerbox.get_position(*self.axis)[self.axis.upper()] - end_position) > 0.01:
            self.log.info(
                f"waiting for flip mount: {self.axis} = "
                f"{self.tigerbox.get_position(*self.axis)[self.axis.upper()] / 10000} -> {POSITIONS[position_name] / 10000} mm"
            )
            time.sleep(1.0)
        self.log.info(f"Flip mount {self.id} moved to position {position_name}")

    @property
    def flip_time_ms(self) -> int:
        """
        Get the time it takes to flip the mount in milliseconds.

        :raises ValueError: If the flip mount is not connected or if the flip time cannot be retrieved
        :return: Flip time in milliseconds
        :rtype: int
        """
        speed_mm_s = self.tigerbox.get_speed(self.axis)
        flip_time_ms = int(
            abs(POSITIONS[list(POSITIONS.keys())[1]] - POSITIONS[list(POSITIONS.keys())[0]])
            / STEPS_PER_UM
            / speed_mm_s[self.axis.upper()]
        )
        return flip_time_ms

    def close(self) -> None:
        """
        Close the stage.
        """
        self.log.info(f"closing flip mount.")
        pass

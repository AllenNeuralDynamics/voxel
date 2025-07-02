from time import sleep
from typing import Dict, Optional

from pylablib.devices import Thorlabs

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.flip_mount.base import BaseFlipMount

VALID_POSITIONS = [0, 1]
FLIP_TIME_RANGE_MS = (500, 2800, 100)
POSITIONS = dict()


class MFF101FlipMount(BaseFlipMount):
    """
    ThorlabsFlipMount class for handling Thorlabs flip mount devices.
    """

    def __init__(self, id: str, positions: Dict[str, int]) -> None:
        """
        Initialize the ThorlabsFlipMount object.

        :param id: Flip mount ID
        :type id: str
        :param positions: Dictionary of positions
        :type positions: dict
        :raises ValueError: If an invalid position is provided
        """
        super().__init__(id)
        self._inst: Optional[Thorlabs.MFF] = None
        self._connect()
        for key, value in positions.items():
            if value not in VALID_POSITIONS:
                raise ValueError(
                    f"Invalid position {key} for Thorlabs flip mount.\
                    Valid positions are {VALID_POSITIONS}"
                )
            POSITIONS[key] = value
        position_idx = self._inst.get_state()
        self._position = next((key for key, value in POSITIONS.items() if value == position_idx), "Unknown")

    def _connect(self) -> None:
        """
        Connect to the flip mount.

        :raises Exception: If connection to the flip mount fails
        """
        try:
            self._inst = Thorlabs.MFF(conn=self.id)
            self.flip_time_ms = FLIP_TIME_RANGE_MS[0]  # min flip time
        except Exception as e:
            self.log.error(f"Could not connect to flip mount {self.id}: {e}")
            raise e

    def _disconnect(self) -> None:
        """
        Disconnect the flip mount.
        """
        if self._inst is not None:
            self._inst.close()
            self._inst = None
            self.log.info(f"Flip mount {self.id} disconnected")

    def wait(self) -> None:
        """
        Wait for the flip mount to finish flipping.
        """
        sleep(self.flip_time_ms * 1e-3)  # type: ignore

    def toggle(self, wait: bool = False) -> None:
        """
        Toggle the flip mount position.

        :param wait: Whether to wait for the flip mount to finish moving, defaults to False
        :type wait: bool, optional
        :raises ValueError: If the flip mount is not connected
        """
        if self._inst is None:
            raise ValueError("Flip mount not connected")
        new_pos = 0 if self._inst.get_state() == 1 else 1
        self._inst.move_to_state(new_pos)
        if wait:
            self.wait()

    @property
    def position(self) -> Optional[str]:
        """
        Get the current position of the flip mount.

        :raises ValueError: If the flip mount is not connected
        :return: Current position of the flip mount
        :rtype: str | None
        """
        return self._position

    @position.setter
    def position(self, position_name: str) -> None:
        """
        Set the flip mount to a specific position.

        :param position_name: Position name
        :type position_name: str
        :raises ValueError: If the flip mount is not connected or if an invalid position is provided
        """
        if self._inst is None:
            raise ValueError("Flip mount not connected")
        if position_name not in POSITIONS:
            raise ValueError(f"Invalid position {position_name}. Valid positions are {list(POSITIONS.keys())}")
        self._inst.move_to_state(POSITIONS[position_name])
        self._position = position_name
        self.log.info(f"Flip mount {self.id} moved to position {position_name}")

    @DeliminatedProperty(minimum=FLIP_TIME_RANGE_MS[0], maximum=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> int:
        """
        Get the time it takes to flip the mount in milliseconds.

        :raises ValueError: If the flip mount is not connected or if the flip time cannot be retrieved
        :return: Flip time in milliseconds
        :rtype: int
        """
        if self._inst is None:
            raise ValueError("Flip mount not connected")
        try:
            parameters = self._inst.get_flipper_parameters()
            flip_time_ms: int = int((parameters.transit_time) * 1e3)
        except Exception:
            raise ValueError("Could not get flip time")
        return flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float) -> None:
        """
        Set the time it takes to flip the mount in milliseconds.

        :param time_ms: Flip time in milliseconds
        :type time_ms: float
        :raises ValueError: If the flip mount is not connected or if an invalid flip time is provided
        """
        if self._inst is None:
            raise ValueError("Flip mount not connected")
        if not isinstance(time_ms, (int, float)) or time_ms <= 0:
            raise ValueError("Switch time must be a positive number")
        clamped_time_ms = int(max(FLIP_TIME_RANGE_MS[0], min(time_ms, FLIP_TIME_RANGE_MS[1])))
        try:
            self._inst.setup_flipper(transit_time=clamped_time_ms / 1000)
            self.log.info(f"Flip mount {self.id} switch time set to {clamped_time_ms} ms")
        except Exception as e:
            raise ValueError(f"Could not set flip time: {e}")

    def close(self) -> None:
        """Close the flip mount connection."""
        self.log.info(f"closing flip mount.")
        self._disconnect()

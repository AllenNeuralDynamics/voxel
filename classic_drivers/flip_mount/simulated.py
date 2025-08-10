from time import sleep
from typing import Literal, Dict

from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.flip_mount.base import BaseFlipMount

VALID_POSITIONS = [0, 1]
FLIP_TIME_RANGE_MS = (500.0, 2800.0, 100.0)  # min, max, step
POSITIONS = {}


class SimulatedFlipMount(BaseFlipMount):
    """
    SimulatedFlipMount class for handling simulated flip mount devices.
    """

    def __init__(self, id: str, conn: object, positions: Dict[str, int]) -> None:
        """
        Initialize the SimulatedFlipMount object.

        :param id: Flip mount ID
        :type id: str
        :param conn: Connection object
        :type conn: object
        :param positions: Dictionary of positions
        :type positions: dict
        :raises ValueError: If an invalid position is provided
        """
        super().__init__(id)
        self._conn = conn
        self._positions = positions
        self._inst: Literal[0, 1] = None
        for key, value in positions.items():
            if value not in VALID_POSITIONS:
                raise ValueError(
                    f"Invalid position {key} for Thorlabs flip mount.\
                    Valid positions are {VALID_POSITIONS}"
                )
            POSITIONS[key] = value
        self._connect()

    def _connect(self) -> None:
        """
        Connect to the flip mount.
        """
        self.position = next(iter(self._positions))  # set to first position
        self.flip_time_ms: float = FLIP_TIME_RANGE_MS[0]  # min flip time

    def close(self) -> None:
        """
        Close the flip mount connection.
        """
        self._inst = None

    def wait(self) -> None:
        """
        Wait for the flip mount to finish flipping.
        """
        sleep(self.flip_time_ms * 1e-3)

    def toggle(self, wait: bool = False) -> None:
        """
        Toggle the flip mount position.

        :param wait: Whether to wait for the flip mount to finish moving, defaults to False
        :type wait: bool, optional
        """
        new_pos = 0 if self._inst == 1 else 1
        self._inst = new_pos
        if wait:
            self.wait()

    @property
    def position(self) -> str:
        """
        Get the current position of the flip mount.

        :return: Current position of the flip mount
        :rtype: str
        """
        return next((key for key, value in self._positions.items() if value == self._inst), "Unknown")

    @position.setter
    def position(self, new_position: str) -> None:
        """
        Set the flip mount to a specific position.

        :param new_position: New position name
        :type new_position: str
        :raises ValueError: If an invalid position is provided
        :raises Exception: If any other error occurs
        """
        try:
            self._inst = self._positions[new_position]
        except KeyError:
            raise ValueError(f"Invalid position {new_position}. Valid positions are {list(self._positions.keys())}")
        except Exception as e:
            raise e

    @DeliminatedProperty(minimum=FLIP_TIME_RANGE_MS[0], maximum=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> float:
        """
        Get the time it takes to flip the mount in milliseconds.

        :return: Flip time in milliseconds
        :rtype: float
        """
        return self._flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float) -> None:
        """
        Set the time it takes to flip the mount in milliseconds.

        :param time_ms: Flip time in milliseconds
        :type time_ms: float
        """
        self.log.info(f"Setting flip_time_ms to {time_ms}")
        self.log.info(f"FLIP_TIME_RANGE_MS is {FLIP_TIME_RANGE_MS}")
        self._flip_time_ms = time_ms

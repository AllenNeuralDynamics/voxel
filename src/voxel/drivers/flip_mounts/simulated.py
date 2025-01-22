from time import sleep
from typing import Literal

from voxel.devices.flip_mount import VoxelFlipMount
from voxel.utils.descriptors.deliminated import deliminated_float

FLIP_TIME_RANGE_MS: tuple[float, float, float] = (500.0, 2800.0, 100.0)  # min, max, step


class SimulatedFlipMount(VoxelFlipMount):
    """Simulated Flip Mount for testing without hardware. \n
    :param conn: Connection string - serial no.
    :param position_1: Name of the first position
    :param position_2: Name of the second position
    :param name: Provide a unique device name
    :type conn: str
    :type position_1: str
    :type position_2: str
    :type name: str
    """

    def __init__(self, conn, position_1: str, position_2: str, name: str = ""):
        super().__init__(name)
        self._conn = conn
        self._position_1 = self._sanitize_string(position_1)
        self._position_2 = self._sanitize_string(position_2)
        self._positions = {0: self._position_1, 1: self._position_2}
        self._inst: int = 0
        self._flip_time_ms: float = FLIP_TIME_RANGE_MS[0]  # min flip time

    def close(self):
        """Close the connection to the flip mount."""
        self._inst = 0

    def wait(self):
        """Wait for the flip mount to finish flipping.
        Note: This function is blocking."""
        sleep(self.flip_time_ms * 1e-3)

    def toggle(self, wait=False):
        """Toggle the flip mount position. \n
        :param wait: Wait for the flip mount to finish flipping. Default: False
        """
        self._inst = 0 if self._inst else 1
        if wait:
            self.wait()

    @property
    def position(self) -> str:
        """Position of the flip mount. \n
        :return: Name of the current position.
        :rtype: str
        """
        return self._positions[self._inst]

    @position.setter
    def position(self, position_name: str):
        """Set the flip mount to a specific position by name. \n
        :param position: Name of the position to set the flip mount to.
        :type position: str
        :raises ValueError: If the position is not found in the available positions.
        """
        position_name = position_name.lower()
        if new_position := next((k for k, v in self._positions.items() if v == position_name.lower()), None):
            assert new_position in [0, 1], f"Invalid position {position_name}. Valid positions are {self._positions}"
            self._inst = new_position
        else:
            self.log.error(f"Invalid position {position_name}. Valid positions are {self._positions}")

    @deliminated_float(min_value=FLIP_TIME_RANGE_MS[0], max_value=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> float:
        """Time it takes to flip the mount in milliseconds.
        :return: Time in milliseconds
        :rtype: float
        """
        return self._flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float):
        """Set the flip time in milliseconds. \n
        :param time_ms: Time in milliseconds to flip the mount.
        :type time_ms: float
        """
        self._flip_time_ms = time_ms

    @staticmethod
    def _sanitize_string(string: str) -> str:
        return string.lower().replace(" ", "_")

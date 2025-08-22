import time

from voxel.devices.interfaces.rotation_axis import VoxelRotationAxis


class SimulatedRotationAxis(VoxelRotationAxis):
    """Simulated rotation axis implementation.
    :param name: Unique identifier for the device
    :type name: str.
    """

    def __init__(self, name: str) -> None:
        """Constructor for the SimulatedRotationAxis class."""
        super().__init__(name=name)
        self._position_deg = 0.0
        self._target_position_deg = 0.0
        self._speed_deg_s = 10.0
        self._movement_start_time = None

    @property
    def position_deg(self) -> float:
        """Return the current position of the rotation axis in degrees.
        :return: The current position in degrees
        :rtype: float.
        """
        if self._movement_start_time is not None:
            elapsed_time = time.time() - self._movement_start_time
            distance = self._speed_deg_s * elapsed_time
            direction = 1 if self._target_position_deg > self._position_deg else -1
            current_position = self._position_deg + direction * min(
                distance,
                abs(self._target_position_deg - self._position_deg),
            )

            if abs(current_position - self._target_position_deg) < 0.01:
                self._position_deg = self._target_position_deg
                self._movement_start_time = None
            else:
                return current_position

        return self._position_deg

    @position_deg.setter
    def position_deg(self, value: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param position: The new position in degrees
        :type position: float.
        """
        self._target_position_deg = value
        self._movement_start_time = time.time()

    @property
    def speed_deg_s(self) -> float:
        """Return the speed of the rotation axis in degrees per second.
        :return: The speed in degrees per second
        :rtype: float.
        """
        return self._speed_deg_s

    @speed_deg_s.setter
    def speed_deg_s(self, value: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param speed: The new speed in degrees per second
        :type speed: float.
        """
        if value <= 0:
            raise ValueError('Speed must be positive')
        self._speed_deg_s = value

    @property
    def is_moving(self) -> bool:
        """Check if the rotation axis is moving.
        :return: True if moving, False otherwise
        :rtype: bool.
        """
        return self._movement_start_time is not None

    def await_movement(self, timeout: float | None = None, check_interval: float = 1) -> None:
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float.
        """
        # Current implementation does not support timeout
        while self.is_moving:
            self.log.debug(
                '\n\tMoving to %s degrees\n\tCurrent position: %.2f degrees',
                self._target_position_deg,
                self.position_deg,
            )
            time.sleep(check_interval)
            _ = self.position_deg  # This updates the position

    def close(self) -> None:
        """Close the connection to the rotation axis."""
        self._movement_start_time = None
        self.log.info('Rotation axis %s closed.', self.uid)

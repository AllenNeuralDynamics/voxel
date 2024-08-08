import time
from typing import Optional
from voxel.devices.rotation_axis import BaseRotationAxis


class SimulatedRotationAxis(BaseRotationAxis):
    """Simulated rotation axis implementation.
    :param id: Unique identifier for the device
    :type id: str
    """
    def __init__(self, id: str) -> None:
        """Constructor for the SimulatedRotationAxis class."""
        super().__init__(id)
        self._position_deg = 0.0
        self._target_position_deg = 0.0
        self._speed_deg_s = 10.0
        self._movement_start_time = None

    @property
    def position_deg(self) -> float:
        """Return the current position of the rotation axis in degrees.
        :return: The current position in degrees
        :rtype: float
        """
        if self._movement_start_time is not None:
            elapsed_time = time.time() - self._movement_start_time
            distance = self._speed_deg_s * elapsed_time
            direction = 1 if self._target_position_deg > self._position_deg else -1
            current_position = self._position_deg + direction * min(distance,
                                                                    abs(self._target_position_deg - self._position_deg))

            if abs(current_position - self._target_position_deg) < 0.01:
                self._position_deg = self._target_position_deg
                self._movement_start_time = None
            else:
                return current_position

        return self._position_deg

    @position_deg.setter
    def position_deg(self, position: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param position: The new position in degrees
        :type position: float
        """
        self._target_position_deg = position
        self._movement_start_time = time.time()

    @property
    def speed_deg_s(self) -> float:
        """Return the speed of the rotation axis in degrees per second.
        :return: The speed in degrees per second
        :rtype: float
        """
        return self._speed_deg_s

    @speed_deg_s.setter
    def speed_deg_s(self, speed: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param speed: The new speed in degrees per second
        :type speed: float
        """
        if speed <= 0:
            raise ValueError("Speed must be positive")
        self._speed_deg_s = speed

    @property
    def is_moving(self) -> bool:
        """Check if the rotation axis is moving.
        :return: True if moving, False otherwise
        :rtype: bool
        """
        return self._movement_start_time is not None

    def wait_until_stopped(self, timeout: Optional[float] = None, check_interval: float = 1) -> None:
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float
        """
        # Current implementation does not support timeout
        while self.is_moving:
            self.log.debug(f'\n\tMoving to {self._target_position_deg} degrees'
                           f'\n\tCurrent position: {self.position_deg:.2f} degrees')
            time.sleep(check_interval)
            _ = self.position_deg  # This updates the position

    def close(self) -> None:
        """Close the connection to the rotation axis."""
        self._movement_start_time = None
        self.log.info(f"Rotation axis {self.id} closed.")


# Example usage
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.DEBUG)
    axis = SimulatedRotationAxis("test_axis")

    print("Moving to 90 degrees...")
    axis.position_deg = 90
    axis.wait_until_stopped()
    print(f"Reached position: {axis.position_deg:.2f}")

    print("Changing speed and moving to 180 degrees...")
    axis.speed_deg_s = 20
    axis.position_deg = 180
    axis.wait_until_stopped()
    print(f"Reached position: {axis.position_deg:.2f}")

    axis.close()
    print("Device closed.")
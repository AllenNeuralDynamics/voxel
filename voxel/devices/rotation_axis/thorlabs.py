from typing import Optional
from pylablib.devices import Thorlabs

from voxel.devices.error import VoxelDeviceError
from voxel.devices.rotation_axis import BaseRotationAxis
import time

MIN_POSITION_DEG = 0
MAX_POSITION_DEG = 360
MIN_SPEED_DEG_S = 0.005
MAX_SPEED_DEG_S = 10

MODEL = 'K10CR1'


class ThorlabsRotationAxis(BaseRotationAxis):
    """Thorlabs rotation mount axis implementation.
    :param id: Unique identifier for the device
    :param serial_number: Serial number of the rotation mount
    :type id: str
    :type serial_number: str
    :raises VoxelDeviceError: If the rotation mount with the specified serial number is not found
    """
    def __init__(self, id: str, serial_number: str):
        """Constructor for the ThorlabsRotationAxis class."""
        super().__init__(id)
        self.serial_number = serial_number
        model = MODEL  # used to determine the step to scale units of the device

        try:
            devices = Thorlabs.list_kinesis_devices()
            for device in devices:
                instance = Thorlabs.Kinesis(conn=device[0], scale=model) # type: ignore
                info = instance.get_device_info()
                if info.serial_no == serial_number:
                    self._instance = instance
                    break
            else:
                raise VoxelDeviceError(f'Could not find rotation mount with serial number {serial_number}')
        except Exception as e:
            raise VoxelDeviceError(f'Could not initialize rotation mount with serial number {serial_number} - Error: {str(e)}')

    @property
    def position_deg(self) -> float:
        """Return the current position of the rotation axis in degrees.
        :return: The current position in degrees
        :rtype: float
        """
        return self._instance.get_position()

    @position_deg.setter
    def position_deg(self, position_deg: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param position: The new position in degrees
        :type position: float
        """
        if position_deg < MIN_POSITION_DEG or position_deg > MAX_POSITION_DEG:
            raise ValueError(f'Position {position_deg} must be between '
                             f'{MIN_POSITION_DEG} and {MAX_POSITION_DEG}')
        self._instance.move_to(position_deg)
        self.log.info(f'Rotation mount {self.serial_number} commanded '
                      f'to move to position {position_deg} deg')

    @property
    def speed_deg_s(self) -> float:
        """Return the speed of the rotation axis in degrees per second.
        :return: The speed in degrees per second
        :rtype: float
        """
        velocity_parameters = self._instance.get_velocity_parameters()
        return velocity_parameters.max_velocity

    @speed_deg_s.setter
    def speed_deg_s(self, speed_deg_s: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param speed: The new speed in degrees per second
        :type speed: float
        """
        if speed_deg_s < MIN_SPEED_DEG_S or speed_deg_s > MAX_SPEED_DEG_S:
            raise ValueError(f'Speed {speed_deg_s} deg/s must be between '
                             f'{MIN_SPEED_DEG_S} and {MAX_SPEED_DEG_S} deg/s')
        self._instance.set_velocity_parameters(max_velocity=speed_deg_s)
        self.log.info(f'Rotation mount {self.serial_number} set '
                      f'to speed {speed_deg_s} deg/s')

    @property
    def is_moving(self) -> bool:
        """Check if the rotation axis is moving.
        :return: True if moving, False otherwise
        :rtype: bool
        """
        status = self._instance.get_status()
        return status.is_moving

    def wait_until_stopped(self, timeout: Optional[float] = None, check_interval: float = 0.1):
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float
        """
        start_time = time.time()
        while self.is_moving:
            time.sleep(check_interval)
            if timeout is not None and time.time() - start_time > timeout:
                self.log.warning(f'Rotation mount {self.serial_number} '
                                 f'did not stop within the specified timeout of {timeout} seconds')
                break

        if not self.is_moving:
            self.log.info(f'Rotation mount {self.serial_number} stopped at position {self.position_deg:.2f} deg')
        else:
            self.log.warning(f'Rotation mount {self.serial_number} is still moving')

    def close(self) -> None:
        """Close the connection to the rotation mount."""
        self._instance.close()
        self.log.info(f'Rotation mount {self.serial_number} closed')


# Example usage
if __name__ == '__main__':
    axis = ThorlabsRotationAxis("unique_id", "SERIAL_NUMBER_HERE")

    print(f"Initial position: {axis.position_deg:.2f} degrees")
    print(f"Initial speed: {axis.speed_deg_s:.2f} deg/s")

    new_position = 90.0
    print(f"Moving to {new_position} degrees...")
    axis.position_deg = new_position
    axis.wait_until_stopped(timeout=30)  # Wait up to 30 seconds
    print(f"New position: {axis.position_deg:.2f} degrees")

    new_speed = 5.0
    print(f"Setting speed to {new_speed} deg/s")
    axis.speed_deg_s = new_speed
    print(f"New speed: {axis.speed_deg_s:.2f} deg/s")

    axis.close()
    print("Device closed.")
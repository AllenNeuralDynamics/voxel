import time

from pylablib.devices import Thorlabs
from pylablib.devices.Thorlabs.kinesis import KinesisMotor

from voxel.devices import VoxelDeviceConnectionError, VoxelRotationAxis

MIN_POSITION_DEG = 0
MAX_POSITION_DEG = 360
MIN_SPEED_DEG_S = 0.005
MAX_SPEED_DEG_S = 10

MODEL = 'K10CR1'


class ThorlabsRotationAxis(VoxelRotationAxis):
    """Thorlabs rotation mount axis implementation.
    :param name: Unique identifier for the device
    :param serial_number: Serial number of the rotation mount
    :type name: str
    :type serial_number: str
    :raises VoxelDeviceError: If the rotation mount with the specified serial number is not found.
    """

    def __init__(self, name: str, serial_number: str):
        """Constructor for the ThorlabsRotationAxis class."""
        super().__init__(name)
        self.serial_number = serial_number
        model = MODEL  # used to determine the step to scale units of the device

        def get_kinesis_motor() -> KinesisMotor:
            devices = Thorlabs.list_kinesis_devices()
            for device in devices:
                instance = KinesisMotor(conn=device[0], scale=model)
                info = instance.get_device_info()
                if info.serial_no == serial_number:
                    return instance
            msg = f'Could not find rotation mount with serial number {serial_number}'
            raise VoxelDeviceConnectionError(msg)

        try:
            self._instance = get_kinesis_motor()
        except Exception as e:
            msg = f'Could not initialize rotation mount with serial number {serial_number} - Error: {e!s}'
            raise VoxelDeviceConnectionError(msg) from e

    @property
    def position_deg(self) -> float:
        """Return the current position of the rotation axis in degrees.
        :return: The current position in degrees
        :rtype: float.
        """
        return self._instance.get_position()

    @position_deg.setter
    def position_deg(self, value: float) -> None:
        """Set the position of the rotation axis in degrees.
        :param position_deg: The new position in degrees
        :type position_deg: float.
        """
        if value < MIN_POSITION_DEG or value > MAX_POSITION_DEG:
            msg = f'Position {value} must be between {MIN_POSITION_DEG} and {MAX_POSITION_DEG}'
            raise ValueError(msg)
        self._instance.move_to(value)
        self.log.info('Rotation mount %s commanded to move to position %s deg', self.serial_number, value)

    @property
    def speed_deg_s(self) -> float:
        """Return the speed of the rotation axis in degrees per second.
        :return: The speed in degrees per second
        :rtype: float.
        """
        velocity_parameters = self._instance.get_velocity_parameters()
        return velocity_parameters.max_velocity

    @speed_deg_s.setter
    def speed_deg_s(self, value: float) -> None:
        """Set the speed of the rotation axis in degrees per second.
        :param speed_deg_s: The new speed in degrees per second
        :type speed_deg_s: float.
        """
        if value < MIN_SPEED_DEG_S or value > MAX_SPEED_DEG_S:
            msg = f'Speed {value} deg/s must be between {MIN_SPEED_DEG_S} and {MAX_SPEED_DEG_S} deg/s'
            raise ValueError(msg)
        self._instance.setup_velocity(max_velocity=value)
        self.log.info('Rotation mount %s set to speed %s deg/s', self.serial_number, value)

    @property
    def is_moving(self) -> bool:
        """Check if the rotation axis is moving.
        :return: True if moving, False otherwise
        :rtype: bool.
        """
        return self._instance.is_moving()

    def await_movement(self, timeout: float | None = None, check_interval: float = 0.1):
        """Wait until the rotation axis has stopped moving.
        :param timeout: Maximum time to wait for the rotation axis to stop moving
        :param check_interval: Time interval between checks
        :type timeout: float
        :type check_interval: float.
        """
        start_time = time.time()
        while self.is_moving:
            time.sleep(check_interval)
            if timeout is not None and time.time() - start_time > timeout:
                self.log.warning(
                    'Rotation mount %s did not stop within the specified timeout of %s seconds',
                    self.serial_number,
                    timeout,
                )
                break

        if not self.is_moving:
            self.log.info('Rotation mount %s stopped at position %.2f deg', self.serial_number, self.position_deg)
        else:
            self.log.warning('Rotation mount %s is still moving', self.serial_number)

    def close(self) -> None:
        """Close the connection to the rotation mount."""
        self._instance.close()
        self.log.info('Rotation mount %s closed', self.serial_number)


# Example usage
if __name__ == '__main__':
    axis = ThorlabsRotationAxis('unique_id', 'SERIAL_NUMBER_HERE')

    print(f'Initial position: {axis.position_deg:.2f} degrees')
    print(f'Initial speed: {axis.speed_deg_s:.2f} deg/s')

    new_position = 90.0
    print(f'Moving to {new_position} degrees...')
    axis.position_deg = new_position
    axis.await_movement(timeout=30)  # Wait up to 30 seconds
    print(f'New position: {axis.position_deg:.2f} degrees')

    new_speed = 5.0
    print(f'Setting speed to {new_speed} deg/s')
    axis.speed_deg_s = new_speed
    print(f'New speed: {axis.speed_deg_s:.2f} deg/s')

    axis.close()
    print('Device closed.')

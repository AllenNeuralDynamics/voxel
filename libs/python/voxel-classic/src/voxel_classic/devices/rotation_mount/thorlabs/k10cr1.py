import logging
from typing import List, Tuple

from pylablib.devices import Thorlabs
from voxel_classic.devices.rotation_mount.base import BaseRotationMount

MIN_POSITION_DEG = 0
MAX_POSITION_DEG = 360

MIN_SPEED_DEG_S = 0.005
MAX_SPEED_DEG_S = 10


class K10CR1Mount(BaseRotationMount):
    """
    RotationMount class for handling Thorlabs K10CR1 rotation mount devices.
    """

    def __init__(self, id: str):
        """
        Initialize the RotationMount object.

        :param id: Rotation mount ID
        :type id: str
        :raises ValueError: If the rotation mount ID is not valid
        """
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)
        self.id = id  # serial number of rotation mount
        # this is used to determine the step to scale units of the device
        model = "K10CR1"
        # lets find the device using pyvisa
        devices: List[Tuple[str, str]] = Thorlabs.list_kinesis_devices()
        # device = [(serial number, name)]
        try:
            for device in devices:
                # uses the MFF class within
                # devices/Thorlabs/kinesis of pylablib
                rotation_mount = Thorlabs.Kinesis(conn=device[0], scale=model)
                info = rotation_mount.get_device_info()
                if info.serial_no == id:
                    self.rotation_mount = rotation_mount
                    break
        except Exception:
            self.log.debug(f"{id} is not a valid thorabs rotation mount")
            raise ValueError(f"could not find power meter with id {id}")

    @property
    def position_deg(self) -> float:
        """
        Get the current position of the rotation mount in degrees.

        :return: Current position in degrees
        :rtype: float
        """
        # returns degree position of the rotation mount
        return self.rotation_mount.get_position()

    @position_deg.setter
    def position_deg(self, position_deg: float) -> None:
        """
        Set the position of the rotation mount in degrees.

        :param position_deg: Position in degrees
        :type position_deg: float
        :raises ValueError: If the position is out of range
        """
        if position_deg < MIN_POSITION_DEG or position_deg > MAX_POSITION_DEG:
            raise ValueError(f"position {position_deg} must be between" f"{MIN_POSITION_DEG} and {MAX_POSITION_DEG}")
        self.rotation_mount.move_to(position_deg)
        self.log.info(f"rotation mount {self.id} moved" f"to position {position_deg} deg")

    @property
    def speed_deg_s(self) -> float:
        """
        Get the speed of the rotation mount in degrees per second.

        :return: Speed in degrees per second
        :rtype: float
        """
        # lets only query the maximum velocity
        velocity_parameters = self.rotation_mount.get_velocity_parameters()
        return velocity_parameters.max_velocity

    @speed_deg_s.setter
    def speed_deg_s(self, speed_deg_s: float) -> None:
        """
        Set the speed of the rotation mount in degrees per second.

        :param speed_deg_s: Speed in degrees per second
        :type speed_deg_s: float
        :raises ValueError: If the speed is out of range
        """
        if speed_deg_s < MIN_SPEED_DEG_S or speed_deg_s > MAX_SPEED_DEG_S:
            raise ValueError(
                f"speed {speed_deg_s} deg/s must be between" f"{MIN_SPEED_DEG_S} and {MAX_SPEED_DEG_S} deg/s"
            )
        self.rotation_mount.set_velocity_parameters(max_velocity=speed_deg_s)
        self.log.info(f"rotation mount {self.id} set" f"to speed {speed_deg_s} deg/s")

    def close(self) -> None:
        """
        Close the rotation mount connection.
        """
        # inherited close property from kinesis in pylablib
        self.rotation_mount.close()
        self.log.info(f"rotation mount {self.id} closed")

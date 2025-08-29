import logging

from coherent_lasers.genesis_mx.commands import OperationMode
from coherent_lasers.genesis_mx.driver import GenesisMX
from voxel.devices.laser.base import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

INIT_POWER_MW = 10.0


class GenesisMXLaser(VoxelLaser):
    """Genesis MX Laser device class."""

    def __init__(self, uid: str, serial_id: str, wavelength: int, max_power_mw: int) -> None:
        """Initialize the Genesis MX Laser.

        Args:
            uid (str): Unique identifier for the laser.
            serial_id (str): The serial ID of the laser.
            wavelength (int): The wavelength of the laser in nanometers.
            max_power_mw (int): The maximum power of the laser in milliwatts.

        Raises:
            ValueError: If the serial number does not match.
        """
        self.log = logging.getLogger(f'{__name__}.{self.__class__.__name__}')
        super().__init__(uid, wavelength=wavelength)
        self._inst = GenesisMX(serial=serial_id)
        if self._inst.head.serial != serial_id:
            err = f'Error initializing laser {serial_id}: serial number mismatch (got {self._inst.head.serial})'
            raise ValueError(err)
        self._inst.mode = OperationMode.PHOTO

        self._max_power_mw = max_power_mw

        self.power_setpoint_mw = INIT_POWER_MW
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        """Get the wavelength of the laser.

        :return: The wavelength of the laser in nanometers.
        :rtype: int
        """
        return self._wavelength

    def enable(self) -> None:
        """Enable the laser."""
        self._inst.enable()

    def disable(self) -> None:
        """Disable the laser."""
        self._inst.disable()

    def close(self) -> None:
        """Close the connection to the laser."""
        self.log.info('closing laser.')
        self.disable()

    @property
    def power_mw(self) -> float:
        """Get the current power of the laser.

        :return: The current power of the laser in milliwatts.
        :rtype: float
        """
        return self._inst.power_mw

    def _get_max_power(self) -> float:
        return self._max_power_mw

    @deliminated_float(min_value=0, max_value=_get_max_power)
    def power_setpoint_mw(self) -> float:
        """Get the power setpoint of the laser.

        :return: The power setpoint of the laser in milliwatts.
        :rtype: float
        """
        return self._inst.power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        """Set the power setpoint of the laser.

        :param value: The desired power setpoint in milliwatts.
        :type value: float
        """
        self.log.info('setting power to %s mW', value)
        self._inst.power_mw = value

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser.

        :return: The temperature of the laser in degrees Celsius.
        :rtype: float
        """
        return self._inst.temperature_c

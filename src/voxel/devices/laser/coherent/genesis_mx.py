import logging

from coherent_lasers.genesis_mx.commands import OperationModes
from coherent_lasers.genesis_mx.driver import GenesisMX

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser

INIT_POWER_MW = 10.0


class GenesisMXLaser(BaseLaser):
    """Genesis MX Laser device class."""

    def __init__(self, id: str, wavelength: int, maximum_power_mw: int) -> None:
        """Initialize the Genesis MX Laser.

        :param id: The serial ID of the laser.
        :type id: str
        :param wavelength: The wavelength of the laser in nanometers.
        :type wavelength: int
        :param maximum_power_mw: The maximum power of the laser in milliwatts.
        :type maximum_power_mw: int
        :raises ValueError: If the serial number does not match.
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        super().__init__(id)
        self._conn = id
        try:
            self._inst = GenesisMX(serial=id)
            assert self._inst.head.serial == id
            self._inst.mode = OperationModes.PHOTO
        except AssertionError:
            raise ValueError(f"Error initializing laser {self._conn}, serial number mismatch")
        self.enable()
        self.power_setpoint_mw = INIT_POWER_MW
        type(self).power_setpoint_mw.maximum = maximum_power_mw
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
        if self._inst is None:
            self._inst = GenesisMX(serial=self._conn)
        self._inst.enable()

    def disable(self) -> None:
        """Disable the laser."""
        self._inst.disable()

    def close(self) -> None:
        """Close the connection to the laser."""
        self.log.info("closing laser.")
        self.disable()

    @property
    def power_mw(self) -> float:
        """Get the current power of the laser.

        :return: The current power of the laser in milliwatts.
        :rtype: float
        """
        return self._inst.power_mw

    @DeliminatedProperty(minimum=0, maximum=float("inf"))
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
        self.log.info(f"setting power to {value} mW")
        self._inst.power_mw = value

    @property
    def temperature_c(self) -> float:
        """Get the temperature of the laser.

        :return: The temperature of the laser in degrees Celsius.
        :rtype: float
        """
        return self._inst.temperature_c

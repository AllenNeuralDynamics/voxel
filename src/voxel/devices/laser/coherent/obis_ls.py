from obis_laser import ObisLS
from serial import Serial
from typing import Union, Dict

from voxel.descriptors.deliminated_property import DeliminatedProperty

from ..base import BaseLaser
from .obis_lx import obis_modulation_getter, obis_modulation_setter

MODULATION_MODES = {"off": "CWP", "analog": "ANALOG", "digital": "DIGITAL", "mixed": "MIXED"}


class ObisLSLaser(BaseLaser):
    """
    ObisLSLaser class for handling Coherent Obis LS laser devices.
    """

    def __init__(self, id: str, wavelength: int, port: Union[Serial, str], prefix: str = None) -> None:
        """
        Initialize the ObisLSLaser object.

        :param id: Laser ID
        :type id: str
        :param wavelength: Wavelength in nanometers
        :type wavelength: int
        :param port: Serial port for the laser
        :type port: Serial | str
        :param prefix: Command prefix for the laser, defaults to None
        :type prefix: str, optional
        """
        super().__init__(id)
        self.prefix = prefix
        self._wavelength = wavelength
        self._inst = ObisLS(port, self.prefix)

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

    def enable(self) -> None:
        """
        Enable the laser.
        """
        self._inst.enable()

    def disable(self) -> None:
        """
        Disable the laser.
        """
        self._inst.disable()

    def close(self) -> None:
        """
        Close the laser connection.
        """
        self.log.info("closing laser.")
        self._inst.close()

    @DeliminatedProperty(minimum=0, maximum=lambda self: self._inst.max_power)
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint in milliwatts.

        :return: Power setpoint in milliwatts
        :rtype: float
        """
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: Union[float, int]) -> None:
        """
        Set the power setpoint in milliwatts.

        :param value: Power setpoint in milliwatts
        :type value: float | int
        """
        self._inst.power_setpoint = value

    @property
    def modulation_mode(self) -> str:
        """
        Get the modulation mode.

        :return: Modulation mode
        :rtype: str
        """
        return obis_modulation_getter(self._inst, self.log, modes=MODULATION_MODES)

    @modulation_mode.setter
    def modulation_mode(self, mode: str) -> None:
        """
        Set the modulation mode.

        :param mode: Modulation mode
        :type mode: str
        """
        obis_modulation_setter(self._inst, mode, modes=MODULATION_MODES)

    @property
    def power_mw(self) -> float:
        """
        Get the current power in milliwatts.

        :return: Current power in milliwatts
        :rtype: float
        """
        return self._inst.power_setpoint

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return self._inst.temperature

    @property
    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser
        :rtype: dict
        """
        return self._inst.get_system_status()

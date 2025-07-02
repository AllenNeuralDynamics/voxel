from obis_laser import ObisLX, OperationalCmd, OperationalQuery
from serial import Serial
from typing import Union, Dict, Optional
import logging

from voxel.descriptors.deliminated_property import DeliminatedProperty

from ..base import BaseLaser

MODULATION_MODES: Dict[str, str] = {"off": "CWP", "analog": "ANALOG", "digital": "DIGITAL", "mixed": "MIXED"}


def obis_modulation_getter(instance: ObisLX, logger: logging.Logger, modes: Optional[Dict[str, str]] = None) -> str:
    """
    Get the modulation mode of the laser.

    :param instance: Laser instance
    :type instance: ObisLX
    :param logger: Logger instance
    :type logger: logging.Logger
    :param modes: Modulation modes, defaults to None
    :type modes: dict, optional
    :return: Modulation mode
    :rtype: str
    """
    if modes is None:
        modes = MODULATION_MODES
    mode = instance.get_operational_setting(OperationalQuery.OPERATING_MODE)
    for key, value in modes.items():
        if mode == value:
            return key
    return logger.error(f"Returned {mode}")


def obis_modulation_setter(instance: ObisLX, value: str, modes: Optional[Dict[str, str]] = None) -> None:
    """
    Set the modulation mode of the laser.

    :param instance: Laser instance
    :type instance: ObisLX
    :param value: Modulation mode
    :type value: str
    :param modes: Modulation modes, defaults to None
    :type modes: dict, optional
    :raises ValueError: If the modulation mode is not valid
    """
    if modes is None:
        modes = MODULATION_MODES
    if value not in modes.keys():
        raise ValueError("mode must be one of %r." % modes.keys())
    if modes[value] == "CWP":
        instance.set_operational_setting(OperationalCmd.MODE_INTERNAL_CW, modes[value])
    else:
        instance.set_operational_setting(OperationalCmd.MODE_EXTERNAL, modes[value])


class ObisLXLaser(BaseLaser):
    """
    ObisLXLaser class for handling Coherent Obis LX laser devices.
    """

    def __init__(self, id: str, wavelength: int, port: Union[Serial, str], prefix: Optional[str] = None) -> None:
        """
        Initialize the ObisLXLaser object.

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
        self._inst = ObisLX(port, self.prefix)

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

    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser
        :rtype: dict
        """
        return self._inst.get_system_status()

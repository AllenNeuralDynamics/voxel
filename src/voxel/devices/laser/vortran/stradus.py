from vortran_laser import BoolVal
from vortran_laser import StradusLaser as StradusVortran
from typing import Union, Dict

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser

MODULATION_MODES = {
    "off": {"external_control": BoolVal.OFF, "digital_modulation": BoolVal.OFF},
    "analog": {"external_control": BoolVal.ON, "digital_modulation": BoolVal.OFF},
    "digital": {"external_control": BoolVal.OFF, "digital_modulation": BoolVal.ON},
}


class StradusLaser(BaseLaser):
    """
    StradusLaser class for handling Vortran Stradus laser devices.
    """

    def __init__(self, id: str, port: str, wavelength: int) -> None:
        """
        Initialize the StradusLaser object.

        :param id: Laser ID
        :type id: str
        :param port: Serial port for the laser
        :type port: str
        :param wavelength: Wavelength in nanometers
        :type wavelength: int
        """
        super().__init__(id)
        self._inst = StradusVortran(port)
        self._wavelength = wavelength

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
        if self._inst.external_control == BoolVal.ON:
            return "analog"
        elif self._inst.digital_modulation == BoolVal.ON:
            return "digital"
        else:
            return "off"

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """
        Set the modulation mode.

        :param value: Modulation mode
        :type value: str
        :raises ValueError: If the modulation mode is not valid
        """
        if value not in MODULATION_MODES.keys():
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self._inst, attribute, state)

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

    @property
    def power_mw(self) -> float:
        """
        Get the current power in milliwatts.

        :return: Current power in milliwatts
        :rtype: float
        """
        return self._inst.power

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
        return self._inst.faults

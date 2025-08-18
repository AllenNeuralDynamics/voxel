import random

import numpy
from serial import Serial
from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.laser.base import BaseLaser

MODULATION_MODES = {
    "off": {"external_control_mode": "OFF", "digital_modulation": "OFF"},
    "analog": {"external_control_mode": "ON", "digital_modulation": "OFF"},
    "digital": {"external_control_mode": "OFF", "digital_modulation": "ON"},
}

MAX_POWER_MW = 100


class SimulatedLaser(BaseLaser):
    """
    SimulatedLaser class for handling simulated laser devices.
    """

    def __init__(self, uid: str, id: str, wavelength: int, maximum_power_mw: float = 100) -> None:
        """
        Initialize the SimulatedLaser object.

        :param id: Laser ID
        :type id: str
        :param wavelength: Wavelength in nanometers
        :type wavelength: int
        :param prefix: Prefix for the laser
        :type prefix: str, optional
        :param maximum_power_mw: Maximum power for the laser in mW
        :type maximum_power_mw: float, optional
        """
        super().__init__(uid)
        self._id = id

        self.ser = Serial
        self._wavelength = wavelength
        self._simulated_power_setpoint_mw = 10.0
        self._max_power_mw = maximum_power_mw
        self._modulation_mode = "digital"
        self._temperature = 20.0
        self._cdrh = "ON"
        self._status: list[str] = []

    def enable(self) -> None:
        """
        Enable the laser.
        """
        pass

    def disable(self) -> None:
        """
        Disable the laser.
        """
        pass

    @DeliminatedProperty(minimum=0, maximum=MAX_POWER_MW)
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint in milliwatts.

        :return: Power setpoint in milliwatts
        :rtype: float
        """
        return self._simulated_power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, power_setpoint_mw: float) -> None:  # type: ignore
        """
        Set the power setpoint in milliwatts.

        :param power_setpoint_mw: Power setpoint in milliwatts
        """
        self._simulated_power_setpoint_mw = power_setpoint_mw

    @property
    def power_mw(self) -> float:
        """
        Get the current power in milliwatts.

        :return: Current power in milliwatts
        :rtype: float
        """
        return random.gauss(self._simulated_power_setpoint_mw, 0.1)

    @property
    def modulation_mode(self) -> str:
        """
        Get the modulation mode.

        :return: Modulation mode
        :rtype: str
        """
        return self._modulation_mode

    @modulation_mode.setter
    def modulation_mode(self, value: str) -> None:
        """
        Set the modulation mode.

        :param value: Modulation mode
        :type value: str
        :raises ValueError: If the modulation mode is not valid
        """
        if value not in MODULATION_MODES:
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self, attribute, state)
            self._modulation_mode = value

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return self._temperature + numpy.random.normal(0, 1)

    def status(self) -> list[str]:
        """
        Get the status of the laser.

        :return: Status of the laser
        :rtype: list
        """
        return self._status

    @property
    def cdrh(self) -> str:
        """
        Get the CDRH status.

        :return: CDRH status
        :rtype: str
        """
        return self._cdrh

    @cdrh.setter
    def cdrh(self, value: str) -> None:
        """
        Set the CDRH status.

        :param value: CDRH status
        :type value: str
        """
        self._cdrh = value

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

    def close(self) -> None:
        """
        Close the laser connection.
        """
        pass

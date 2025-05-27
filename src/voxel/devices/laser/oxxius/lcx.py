from typing import Dict, Union

from oxxius_laser import LCX, BoolVal, Cmd, OxxiusController, Query

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser
from voxel.devices.controller.oxxius import L6ccController

class OxxiusLCXLaser(BaseLaser):
    """
    OxxiusLCXLaser class for handling Oxxius LCX laser devices.
    """

    def __init__(
        self, id: str, prefix: str, wavelength: float, port: str = None, controller: L6ccController = None
    ) -> None:
        """
        Initialize an OxxiusLCXLaser instance.

        :param id: Laser identifier.
        :type id: str
        :param prefix: Command prefix for the laser.
        :type prefix: str
        :param wavelength: Wavelength of the laser in nanometers.
        :type wavelength: float
        :param port: Serial port name, defaults to None.
        :type port: str, optional
        :param controller: L6ccController instance, defaults to None.
        :type controller: L6ccController, optional
        :raises ValueError: If both controller and port are None.
        """
        super().__init__(id)

        if controller is None and port is None:
            raise ValueError("Controller and port cannot both be none")

        if controller is None:
            self._controller = LCX(port, self._prefix)
        else:
            self._controller = controller
        self._prefix = prefix
        type(self).power_setpoint_mw.maximum = self.max_power
        self._wavelength = wavelength

    def enable(self) -> None:
        """
        Enable laser emission.

        :return: None
        """
        self._controller.set(Cmd.LaserEmission, BoolVal.ON, self._prefix)

    def disable(self) -> None:
        """
        Disable laser emission.

        :return: None
        """
        self._controller.set(Cmd.LaserEmission, BoolVal.OFF, self._prefix)

    @property
    def wavelength(self) -> float:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers.
        :rtype: float
        """
        return self._wavelength

    @DeliminatedProperty(minimum=0, maximum=float("inf"))
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint in milliwatts.

        :return: Power setpoint in milliwatts.
        :rtype: float
        """
        return float(self._controller.get(Query.LaserPowerSetting, self._prefix))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: Union[float, int]) -> None:
        """
        Set the power setpoint.

        :param value: Power setpoint value.
        :type value: float or int
        :return: None
        """
        if 0 > value > self.max_power:
            reason = f"exceeds maximum power output {self.max_power}mW" if value > self.max_power else "is below 0mW"
            self.log.error(f"Cannot set laser to {value}ml because it {reason}")
        else:
            self._controller.set(Cmd.LaserPower, value, self._prefix)

    @property
    def power_mw(self) -> float:
        """
        Get the current laser power.

        :return: Current laser power in milliwatts.
        :rtype: float
        """
        power_mw_dict = self._controller.get_power_mw()
        return float(power_mw_dict[self._prefix])

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius.
        :rtype: float
        """
        temperature_c_dict = self._controller.get_temperature_c()
        return float(temperature_c_dict[self._prefix])

    @property
    def max_power(self) -> float:
        """
        Get the maximum power in milliwatts.

        :return: Maximum power in milliwatts.
        :rtype: float
        """
        return float(self._controller.get(Query.MaximumLaserPower, self._prefix))

    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser.
        :rtype: dict
        """
        # This should probably return a dict, but currently returns a BoolVal.
        # Adjust as needed for your application.
        return {"emission_key_status": BoolVal(self._controller.get(Query.EmmissionKeyStatus, self._prefix))}

    def close(self) -> None:
        """
        Close the laser connection.

        :return: None
        """
        self.disable()

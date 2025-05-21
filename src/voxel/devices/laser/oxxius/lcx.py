from typing import Dict, Union

from oxxius_laser.oxxius_laser import LCX, BoolVal, Cmd, OxxiusController, Query

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.laser.base import BaseLaser


class OxxiusLCXLaser(BaseLaser):
    """
    OxxiusLCXLaser class for handling Oxxius LCX laser devices.
    """

    def __init__(
        self, id: str,
        wavelength: int,
        prefix: str,
        coefficients: Dict[str, float] = None,
        port: str = None,
        controller: OxxiusController = None,
    ) -> None:
        """_summary_

        :param id: _description_
        :type id: str
        :param wavelength: _description_
        :type wavelength: int
        :param prefix: _description_
        :type prefix: str
        :param coefficients: _description_, defaults to None
        :type coefficients: Dict[str, float], optional
        :param port: _description_, defaults to None
        :type port: str, optional
        :param controller: _description_, defaults to None
        :type controller: OxxiusController, optional
        """
        super().__init__(id)

        if controller is None and port is None:
            raise ValueError("Controller and port cannot both be none")

        self._controller = LCX(port, self._prefix) if controller is None else controller
        self._prefix = prefix
        self._coefficients = coefficients
        self._wavelength = wavelength

    def enable(self) -> None:
        """
        Enable the laser.
        """
        self._controller.enable()

    def disable(self) -> None:
        """
        Disable the laser.
        """
        self._controller.disable()

    @property
    def wavelength(self) -> int:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers
        :rtype: int
        """
        return self._wavelength

    @DeliminatedProperty(minimum=0, maximum=lambda self: self.max_power)
    def power_setpoint_mw(self) -> float:
        """
        Get the power setpoint in milliwatts.

        :return: Power setpoint in milliwatts
        :rtype: float
        """
        return float(self._controller.get(self._prefix, Query.LaserPowerSetting))

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: Union[float, int]) -> None:
        """
        Set the power setpoint.

        :param value: Power setpoint value.
        :type value: float
        """
        if 0 > value > self.max_power:
            reason = (
                f"exceeds maximum power output {self.max_power}mW"
                if value > self.max_power
                else "is below 0mW"
            )
            self.log.error(f"Cannot set laser to {value}ml because it {reason}")
        else:
            self._controller.set(self._prefix, Cmd.LaserPower, value)

    @property
    def power_mw(self) -> float:
        """
        Get the current power in milliwatts.

        :return: Current power in milliwatts
        :rtype: float
        """
        return self._controller.get(self._prefix, Query.LaserPower)

    @property
    def max_power(self) -> float:
        """
        Get the maximum power in milliwatts.

        :return: Maximum power in milliwatts
        :rtype: float
        """
        return self._controller.get(self._prefix, Query.MaximumLaserPower)

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius
        :rtype: float
        """
        return self._controller.temperature

    def status(self) -> Dict[str, Union[str, float]]:
        """
        Get the status of the laser.

        :return: Status of the laser
        :rtype: dict
        """
        return BoolVal(self._controller.get(self._prefix, Query.EmmissionKeyStatus))

    def close(self) -> None:
        """
        Close the laser connection.
        """
        self.disable()
        if self._controller.ser.is_open:
            self._controller.ser.close()

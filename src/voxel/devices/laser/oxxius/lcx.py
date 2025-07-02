from typing import Dict, Union

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.controller.oxxius.lxcc import BoolVal, Cmd, CombinerCmd, CombinerQuery, OxxiusController, Query
from voxel.devices.laser.base import BaseLaser


class OxxiusLCXLaser(BaseLaser):
    """
    OxxiusLCXLaser class for handling Oxxius LCX laser devices.
    """

    def __init__(
        self, id: str, prefix: str, wavelength: float, port: str = None, controller: OxxiusController = None
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
        :param OxxiusController: L6ccController instance, defaults to None.
        :type OxxiusController: L6ccController, optional
        :raises ValueError: If both controller and port are None.
        """
        super().__init__(id)

        if controller is None and port is None:
            raise ValueError("Controller and port cannot both be none")

        if controller is None:
            self._controller = OxxiusController(port=port)
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
        self.log.info("laser enabled")

    def disable(self) -> None:
        """
        Disable laser emission.

        :return: None
        """
        self._controller.set(Cmd.LaserEmission, BoolVal.OFF, self._prefix)
        self.log.info("laser disabled")

    @DeliminatedProperty(minimum=0, maximum=float("inf"))
    def aom_power_mw(self) -> float:
        """
        Get the wavelength of the laser.

        :return: Wavelength in nanometers.
        :rtype: float
        """
        return float(self._controller.get(CombinerQuery.AOMPower, self._prefix))

    @aom_power_mw.setter
    def aom_power_mw(self, value: float) -> None:
        """
        Set the AOM power.

        :param value: AOM power value.
        :type value: float
        :return: None
        """
        if 0 > value > round(self.max_power / 1.1):  # AOM power is capped at - 10% of max power
            reason = f"exceeds maximum power output {self.max_power}mW" if value > self.max_power else "is below 0mW"
            self.log.error(f"Cannot set laser to {value} mW because it {reason}")
        else:
            self._controller.set(CombinerCmd.AOMPower, value, self._prefix)
        self.log.info(f"AOM power set to {value} mW")

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
    def power_setpoint_mw(self, value: float) -> None:
        """
        Set the power setpoint.

        :param value: Power setpoint value.
        :type value: float
        :return: None
        """
        if 0 > value > self.max_power:
            reason = f"exceeds maximum power output {self.max_power}mW" if value > self.max_power else "is below 0mW"
            self.log.error(f"Cannot set laser to {value} mW because it {reason}")
        else:
            self._controller.set(Cmd.LaserPower, value, self._prefix)
        self.log.info(f"power set to {value} mW")

    @property
    def power_mw(self) -> float:
        """
        Get the current laser power.

        :return: Current laser power in milliwatts.
        :rtype: float
        """
        power_mw = self._controller.get(Query.LaserPower, self._prefix)
        return float(power_mw)

    @property
    def temperature_c(self) -> float:
        """
        Get the temperature of the laser in Celsius.

        :return: Temperature in Celsius.
        :rtype: float
        """
        temperature_c = self._controller.get(Query.BasePlateTemperature)
        return float(temperature_c)

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
        self.log.info("laser closed")

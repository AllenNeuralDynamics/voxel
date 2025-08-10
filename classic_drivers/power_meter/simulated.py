import random

from voxel_classic.devices.power_meter.base import BasePowerMeter


class SimulatedPowerMeter(BasePowerMeter):
    """
    SimulatedPowerMeter class for handling simulated power meter devices.

    :param BasePowerMeter: Base class for power meter devices
    :type BasePowerMeter: class
    """

    def __init__(self, id: str, wavelength_nm: float) -> None:
        """
        Initialize the SimulatedPowerMeter object.

        :param id: Power meter ID
        :type id: str
        :param wavelength_nm: Wavelength in nanometers
        :type wavelength_nm: float
        """
        super().__init__(id)
        self._wavelength_nm = wavelength_nm
        self._is_connected = False
        self._connect()

    def _connect(self) -> None:
        """
        Connect to the simulated power meter.
        """
        self._is_connected = True

    def _check_connection(self) -> None:
        """
        Check if the power meter is connected.

        :raises Exception: If the power meter is not connected
        """
        if not self._is_connected:
            raise Exception(f"Device {self.id} is not connected")

    @property
    def power_mw(self) -> float:
        """
        Get the power in milliwatts.

        :return: Power in milliwatts
        :rtype: float
        """
        self._check_connection()
        return max(min(random.gauss(500, 50), 1000), 0)

    @property
    def wavelength_nm(self) -> float:
        """
        Get the wavelength in nanometers.

        :return: Wavelength in nanometers
        :rtype: float
        """
        self._check_connection()
        return self._wavelength_nm

    @wavelength_nm.setter
    def wavelength_nm(self, wavelength: float) -> None:
        """
        Set the wavelength in nanometers.

        :param wavelength: Wavelength in nanometers
        :type wavelength: float
        """
        self._check_connection()
        self._wavelength_nm = wavelength

    def close(self) -> None:
        """
        Close the simulated power meter connection.
        """
        self._is_connected = False

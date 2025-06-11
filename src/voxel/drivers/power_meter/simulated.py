import random

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.interfaces.power_meter import VoxelPowerMeter


class SimulatedPowerMeter(VoxelPowerMeter):
    """
    A simulated power meter device that implements the VoxelPowerMeter interface.
    """

    def __init__(self, name: str, wavelength_nm: float) -> None:
        """
        Initialize the simulated power meter with a specific wavelength.

        Parameters:
        wavelength_nm (float): The wavelength in nanometers.
        """
        super().__init__(name=name)
        self._wavelength_nm = wavelength_nm
        self._is_connected = False
        self._connect()

    def _connect(self):
        """
        Connect to the power meter.
        """
        self._is_connected = True

    def _check_connection(self):
        """
        Check if the device is connected and raise an exception if it's not.
        """
        if not self._is_connected:
            raise VoxelDeviceConnectionError(f"Device {self.name} is not connected")

    @property
    def power_mw(self) -> float:
        """
        Returns:
        float: The power in milliwatts if the power meter is connected, otherwise raises an exception.
        """
        self._check_connection()
        return max(min(random.gauss(500, 50), 1000), 0)

    @property
    def wavelength_nm(self) -> float:
        """
        Returns:
        float: The wavelength in nanometers if the power meter is connected, otherwise raises an exception.
        """
        self._check_connection()
        return self._wavelength_nm

    @wavelength_nm.setter
    def wavelength_nm(self, wavelength: float) -> None:
        """
        Parameters:
        wavelength (float): The new wavelength in nanometers if the power meter is connected, otherwise raises an exception.
        """
        self._check_connection()
        self._wavelength_nm = wavelength

    def close(self) -> None:
        """
        Shutdown the power meter.
        """
        self._is_connected = False

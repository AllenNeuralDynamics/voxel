from typing import Optional

import pyvisa as visa

from voxel_classic.devices.power_meter.base import BasePowerMeter


class ThorlabsPowerMeter(BasePowerMeter):
    """
    ThorlabsPowerMeter class for handling Thorlabs power meter devices.
    """

    def __init__(self, id: str, conn: str) -> None:
        """
        Initialize the ThorlabsPowerMeter object.

        :param id: Power meter ID
        :type id: str
        :param conn: Connection string
        :type conn: str
        """
        super().__init__(id)
        self._conn = conn
        self._inst: Optional[visa.resources.Resource] = None
        self._connect()

    def _connect(self) -> None:
        """
        Connect to the Thorlabs power meter.
        """
        rm = visa.ResourceManager()
        try:
            self._inst = rm.open_resource(self._conn)
            self.log.info(f"Connection to {self._conn} successful")
        except visa.VisaIOError as e:
            self.log.error(f"Could not connect to {self._conn}: {e}")
            raise
        except Exception as e:
            self.log.error(f"Unknown error: {e}")
            raise

    def _check_connection(self) -> None:
        """
        Check if the power meter is connected.

        :raises Exception: If the power meter is not connected
        """
        if self._inst is None:
            raise Exception(f"Device {self.id} is not connected")

    @property
    def power_mw(self) -> float:
        """
        Get the power in milliwatts.

        :return: Power in milliwatts
        :rtype: float
        """
        self._check_connection()
        return float(self._inst.query("MEAS:POW?")) * 1e3  # type: ignore

    @property
    def wavelength_nm(self) -> float:
        """
        Get the wavelength in nanometers.

        :return: Wavelength in nanometers
        :rtype: float
        """
        self._check_connection()
        return float(self._inst.query("SENS:CORR:WAV?"))  # type: ignore

    @wavelength_nm.setter
    def wavelength_nm(self, wavelength: float) -> None:
        """
        Set the wavelength in nanometers.

        :param wavelength: Wavelength in nanometers
        :type wavelength: float
        """
        self._check_connection()
        self._inst.write(f"SENS:CORR:WAV {wavelength}")  # type: ignore
        self.log.info(f"{self.id} - Set wavelength to {wavelength} nm")

    def close(self) -> None:
        """
        Close the power meter connection.
        """
        if self._inst is not None:
            self._inst.close()
            self._inst = None
            self.log.info(f"Disconnected from {self._conn}")
        else:
            self.log.warning(f"Already disconnected from {self._conn}")

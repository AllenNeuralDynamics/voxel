from typing import Optional

import pyvisa as visa

from voxel.devices import VoxelDeviceConnectionError
from voxel.devices.interfaces.power_meter import VoxelPowerMeter


class ThorlabsPowerMeter(VoxelPowerMeter):
    def __init__(self, name: str, conn: str) -> None:
        super().__init__(name)
        self._conn = conn
        self._inst: Optional[visa.resources.Resource] = None
        self._connect()

    def _connect(self):
        """
        Connect to the power meter.
        """
        rm = visa.ResourceManager()
        try:
            self._inst = rm.open_resource(self._conn)
            self._log.info(f"Connection to {self._conn} successful")
        except visa.VisaIOError as e:
            self._log.error(f"Could not connect to {self._conn}: {e}")
            raise VoxelDeviceConnectionError from e
        except Exception as e:
            self._log.error(f"Unknown error: {e}")
            raise VoxelDeviceConnectionError from e

    def _check_connection(self):
        if self._inst is None:
            raise Exception(f"Device {self.name} is not connected")

    @property
    def power_mw(self) -> float:
        self._check_connection()
        return float(self._inst.query("MEAS:POW?")) * 1e3  # type: ignore

    @property
    def wavelength_nm(self) -> float:
        self._check_connection()
        return float(self._inst.query("SENS:CORR:WAV?"))  # type: ignore

    @wavelength_nm.setter
    def wavelength_nm(self, wavelength: float) -> None:
        self._check_connection()
        self._inst.write(f"SENS:CORR:WAV {wavelength}")  # type: ignore
        self._log.info(f"{self.name} - Set wavelength to {wavelength} nm")

    def close(self) -> None:
        if self._inst is not None:
            self._inst.close()
            self._inst = None
            self._log.info(f"Disconnected from {self._conn}")
        else:
            self._log.warning(f"Already disconnected from {self._conn}")

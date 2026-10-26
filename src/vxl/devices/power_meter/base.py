"""Vendor-neutral optical power meter contract."""

from abc import ABC, abstractmethod

from rigup import Device, describe, numeric
from vxl.devices.base import DeviceType


class PowerMeter(Device, ABC):
    """Optional rig device measuring light at the sensor.

    The instrument or calibration workflow defines the measurement location and
    any association with a laser. Registration does not populate Laser.output_power_mw.
    Settling delays and repeated sampling belong to the caller.
    """

    __DEVICE_TYPE__ = DeviceType.POWER_METER

    @property
    @abstractmethod
    @describe(label="Measured Power", units="mW", stream=True)
    def power_mw(self) -> float:
        """Acquire a finite reading in mW; raise for overload or measurement failure.

        Small negative readings from noise or zero correction are valid. Averaging
        is device-specific; this does not wait for the optical source to settle.
        """

    @numeric()
    @abstractmethod
    @describe(label="Wavelength Correction", units="nm")
    def wavelength_nm(self) -> float:
        """Wavelength used for sensor response correction, not a measured wavelength."""

    @wavelength_nm.setter
    @abstractmethod
    def wavelength_nm(self, value: float) -> None:
        """Set the wavelength correction within the sensor's supported range."""

    @abstractmethod
    def close(self) -> None:
        """Release the connection; repeated calls are harmless."""

"""Vendor-neutral optical power meter contract."""

from abc import ABC, abstractmethod

from rigup.device import Device, number, prop

from vxl.devices.base import DeviceType


class PowerMeter(Device, ABC, kind=DeviceType.POWER_METER):
    """Optional rig device measuring light at the sensor.

    The instrument or calibration workflow defines the measurement location and
    any association with a laser. Registration does not populate Laser.output_power_mw.
    Settling delays and repeated sampling belong to the caller.
    """

    @property
    @prop(label="Measured Power", units="mW", stream="fast")
    @abstractmethod
    def power_mw(self) -> float:
        """Acquire a finite reading in mW; raise for overload or measurement failure.

        Small negative readings from noise or zero correction are valid. Averaging
        is device-specific; this does not wait for the optical source to settle.
        """

    @number()
    @prop(label="Wavelength Correction", units="nm")
    @abstractmethod
    def wavelength_nm(self) -> float:
        """Wavelength used for sensor response correction, not a measured wavelength."""

    @wavelength_nm.setter
    @abstractmethod
    def wavelength_nm(self, value: float) -> None:
        """Set the wavelength correction within the sensor's supported range."""

    @abstractmethod
    def dispose(self) -> None:
        """Release the connection; repeated calls are harmless."""

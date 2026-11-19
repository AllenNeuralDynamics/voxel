"""An optical power meter: a sensor that measures the power of the light that reaches it."""

from abc import abstractmethod

from rigup.device import Device
from rigup.interface import number, stream


class PowerMeter(Device, kind="power_meter"):
    """A sensor that measures optical power, such as a bench meter or a photodiode fixed in the beam.

    What a driver must make true:

    - :attr:`power` is ``None`` when there is no valid reading, such as on overload. A small negative reading from
      noise or zero correction is valid. Reading it does not wait for the light source to settle.
    - :attr:`wavelength` is the wavelength used to correct the sensor's response, not a measured wavelength."""

    @property
    @stream(label="Power", units="mW")
    @abstractmethod
    def power(self) -> float | None: ...

    @number()
    @stream(label="Wavelength", units="nm")
    @abstractmethod
    def wavelength(self) -> float: ...

    @wavelength.setter
    @abstractmethod
    def wavelength(self, value: float) -> None: ...


__all__ = ["PowerMeter"]

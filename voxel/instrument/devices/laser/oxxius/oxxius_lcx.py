from oxxius_laser import LCX
from serial import Serial

from utils.descriptors.deliminated_property import deliminated_property
from voxel.instrument.devices.laser.base import VoxelLaser


class OxxiusLCXLaser(VoxelLaser):

    def __init__(self, name: str, port: Serial | str, prefix: str, wavelength: int):
        """
        Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param wavelength: wavelength of laser
        """
        super().__init__(name)
        self._prefix = prefix
        self._inst = LCX(port, self._prefix)
        self._wavelength = wavelength

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    @property
    def wavelength(self) -> int:
        return self._wavelength

    @deliminated_property(minimum=0, maximum=lambda self: self._inst.max_power)
    def power_setpoint_mw(self):
        return float(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float | int):
        self._inst.power_setpoint = value

    @property
    def power_mw(self) -> float:
        return float(self._inst.power)

    @property
    def temperature_c(self) -> float:
        return float(self._inst.temperature)

    def status(self):
        return self.status()

    def close(self):
        self.disable()
        if self._inst.ser.is_open:
            self._inst.ser.close()

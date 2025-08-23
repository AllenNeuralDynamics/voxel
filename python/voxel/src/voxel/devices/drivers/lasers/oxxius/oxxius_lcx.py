from oxxius_laser import LCX
from serial import Serial

from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float


class OxxiusLCXLaser(VoxelLaser):
    def __init__(self, name: str, port: Serial | str, prefix: str, wavelength: int):
        """Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param wavelength: wavelength of laser
        """
        super().__init__(name=name, wavelength=wavelength)
        self._prefix = prefix
        self._inst = LCX(port, self._prefix)

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    @deliminated_float(min_value=0, max_value=lambda self: self._inst.max_power)
    def power_setpoint_mw(self):
        return float(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float):
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

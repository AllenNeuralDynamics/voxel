from oxxius_laser import LCX
from pyparsing import Any
from serial import Serial
from voxel.devices.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float


class OxxiusLCXLaser(VoxelLaser):
    def __init__(self, name: str, port: Serial | str, prefix: str, wavelength: int) -> None:
        """Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param wavelength: wavelength of laser
        """
        super().__init__(uid=name, wavelength=wavelength)
        self._prefix = prefix
        self._inst = LCX(port, self._prefix)

    def enable(self) -> None:
        self._inst.enable()

    def disable(self) -> None:
        self._inst.disable()

    @deliminated_float(min_value=0, max_value=lambda self: self._inst.max_power)
    def power_setpoint_mw(self) -> float:
        return float(self._inst.power_setpoint)

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        self._inst.power_setpoint = value

    @property
    def power_mw(self) -> float:
        return float(self._inst.power)

    @property
    def temperature_c(self) -> float:
        return float(self._inst.temperature)

    def status(self) -> Any:
        return self.status()

    def close(self) -> None:
        self.disable()
        if self._inst.ser.is_open:
            self._inst.ser.close()

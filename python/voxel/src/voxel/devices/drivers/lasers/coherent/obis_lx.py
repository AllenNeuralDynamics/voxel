from obis_laser import ObisLX, OperationalCmd, OperationalQuery
from serial import Serial
from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

MODULATION_MODES: dict[str, str] = {'off': 'CWP', 'analog': 'ANALOG', 'digital': 'DIGITAL', 'mixed': 'MIXED'}


def obis_modulation_getter(instance, logger, modes=None):
    if modes is None:
        modes = MODULATION_MODES
    mode = instance.get_operational_setting(OperationalQuery.OPERATING_MODE)
    for key, value in modes.items():
        if mode == value:
            return key
    logger.error('Returned %s', mode)
    return None


def obis_modulation_setter(instance, value: str, modes=None):
    if modes is None:
        modes = MODULATION_MODES
    if value not in modes:
        raise ValueError('mode must be one of %r.' % modes.keys())
    if modes[value] == 'CWP':
        instance.set_operational_setting(OperationalCmd.MODE_INTERNAL_CW, modes[value])
    else:
        instance.set_operational_setting(OperationalCmd.MODE_EXTERNAL, modes[value])


class ObisLXLaser(VoxelLaser):
    def __init__(self, name: str, wavelength: int, port: Serial | str, prefix: str | None = None):
        """Communicate with specific LBX laser in L6CC Combiner box.

        :param port: comm port for lasers.
        :param prefix: prefix specic to laser.
        :param wavelength: wavelength of laser
        """
        super().__init__(name=name, wavelength=wavelength)
        self.prefix = prefix
        self._inst = ObisLX(port, self.prefix)

    def enable(self):
        self._inst.enable()

    def disable(self):
        self._inst.disable()

    def close(self):
        self._inst.ser.close()

    @deliminated_float(min_value=0, max_value=lambda self: self._inst.max_power)
    def power_setpoint_mw(self):
        return self._inst.power_setpoint

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float):
        self._inst.power_setpoint = value

    @property
    def modulation_mode(self) -> str | None:
        """Get the modulation mode of the laser.

        The modulation mode can be one of two categories:

            - External Control: Analog, Digital, Mixed
            - Internal Control: off (CWP)
        """
        return obis_modulation_getter(self._inst, self.log, modes=MODULATION_MODES)

    @modulation_mode.setter
    def modulation_mode(self, mode: str):
        """Set the modulation mode of the laser.

        Can be one of two categories:
            - External Control - Analog, Digital, Mixed
            - Internal Control - off: CWP

        Args:
            mode: Modulation mode as a string.
        """
        obis_modulation_setter(self._inst, mode, modes=MODULATION_MODES)

    @property
    def power_mw(self) -> float:
        return self._inst.power_setpoint

    @property
    def temperature_c(self) -> float:
        return self._inst.temperature

    def status(self):
        return self._inst.get_system_status()

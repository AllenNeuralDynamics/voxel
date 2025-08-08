import random

from serial import Serial

from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import deliminated_float

MODULATION_MODES = {
    "off": {"external_control_mode": "OFF", "digital_modulation": "OFF"},
    "analog": {"external_control_mode": "ON", "digital_modulation": "OFF"},
    "digital": {"external_control_mode": "OFF", "digital_modulation": "ON"},
}

MAX_POWER_MW = 100


class SimulatedLaser(VoxelLaser):
    def __init__(self, wavelength: int, name: str = "simulated_laser", prefix: str = ""):
        """
        Communicate with specific Simulated laser in Simulated Combiner box.

        :param name: voxel device name for this laser.
        :param prefix: prefix specic to laser.
        """

        self.prefix = prefix
        self.ser = Serial
        self._simulated_power_setpoint_mw = 10.0
        self._max_power_mw = 100.0
        self._modulation_mode = "digital"
        self._temperature = 20.0
        self._cdrh = "ON"
        self._status = []
        super().__init__(name=name, wavelength=wavelength)

    def enable(self):
        self._log.info(f"Enabling {self.uid} laser")
        pass

    def disable(self):
        pass

    @deliminated_float(min_value=0, max_value=MAX_POWER_MW)
    def power_setpoint_mw(self):
        return self._simulated_power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float):
        self._simulated_power_setpoint_mw = value

    @property
    def power_mw(self):
        return random.gauss(self._simulated_power_setpoint_mw, 0.1)

    @property
    def modulation_mode(self):
        return self._modulation_mode

    @modulation_mode.setter
    def modulation_mode(self, value: str):
        if value not in MODULATION_MODES:
            raise ValueError("mode must be one of %r." % MODULATION_MODES.keys())
        for attribute, state in MODULATION_MODES[value].items():
            setattr(self, attribute, state)
            self._modulation_mode = value

    @property
    def temperature_c(self):
        return self._temperature

    def status(self):
        return self._status

    @property
    def cdrh(self):
        return self._cdrh

    @cdrh.setter
    def cdrh(self, value: str):
        self._cdrh = value

    def close(self):
        pass

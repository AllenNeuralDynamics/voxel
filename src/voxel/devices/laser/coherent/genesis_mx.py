import logging
from coherent_lasers.genesis_mx.driver import GenesisMX
from coherent_lasers.genesis_mx.commands import OperationModes
from voxel.devices.laser.base import BaseLaser
from voxel.descriptors.deliminated_property import DeliminatedProperty

INIT_POWER_MW = 10.0


class GenesisMXLaser(BaseLaser):
    def __init__(self, id: str, wavelength: int, maximum_power_mw: int) -> None:
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        super().__init__(id)
        self._conn = id
        try:
            self._inst = GenesisMX(serial=id)
            assert self._inst.head.serial == id
            self._inst.mode = OperationModes.PHOTO
        except AssertionError:
            raise ValueError(f"Error initializing laser {self._conn}, serial number mismatch")
        self.enable()
        self.power_setpoint_mw = INIT_POWER_MW
        type(self).power_setpoint_mw.maximum = maximum_power_mw
        self._wavelength = wavelength

    @property
    def wavelength(self) -> int:
        return self._wavelength

    def enable(self) -> None:
        if self._inst is None:
            self._inst = GenesisMX(serial=self._conn)
        self._inst.enable()

    def disable(self) -> None:
        pass
        self._inst.disable()

    def close(self) -> None:
        self.disable()

    @property
    def power_mw(self) -> float:
        return self._inst.power_mw

    @DeliminatedProperty(minimum=0, maximum=float("inf"))
    def power_setpoint_mw(self) -> float:
        return self._inst.power_setpoint_mw

    @power_setpoint_mw.setter
    def power_setpoint_mw(self, value: float) -> None:
        self.log.info(f"setting power to {value} mW")
        self._inst.power_mw = value

    @property
    def temperature_c(self) -> float:
        """The temperature of the laser in degrees Celsius."""
        return self._inst.temperature_c

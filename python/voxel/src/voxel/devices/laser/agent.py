from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

from voxel.devices.device_agent import DeviceState, VoxelDeviceAgent
from voxel.utils.descriptors.deliminated import DeliminatedFloat

from .base import VoxelLaser


class LaserState(DeviceState):
    wavelength: int
    enabled: bool
    power_setpoint: DeliminatedFloat
    power: float
    temperature: float
    model_config: ClassVar = {'arbitrary_types_allowed': True}  # if needed


class LaserAgent(VoxelDeviceAgent[LaserState]):
    def __init__(self, laser: VoxelLaser, poll_ms: int = 500, executor: ThreadPoolExecutor | None = None) -> None:
        super().__init__(poll_ms=poll_ms, executor=executor)
        self.laser = laser

    @property
    def uid(self) -> str:
        return self.laser.uid

    def set_enable(self, *, on: bool) -> None:
        self.submit_command(lambda: (self.laser.enable() if on else self.laser.disable()))

    def set_power(self, *, power_mw: float) -> None:
        self.submit_command(lambda: setattr(self.laser, 'power_setpoint_mw', float(power_mw)))

    def _read_state(self) -> LaserState:
        return LaserState(
            wavelength=int(self.laser.wavelength),
            enabled=self.laser.is_enabled,
            power_setpoint=self.laser.power_setpoint_mw,
            power=float(self.laser.power_mw),
            temperature=float(self.laser.temperature_c or 0.0),
        )

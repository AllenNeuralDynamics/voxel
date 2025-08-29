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
        self._max_allowed_power_setpoint_diff = 5  # mW
        self._enabled_diff_percent = 10.0  # %

    @property
    def uid(self) -> str:
        return self.laser.uid

    async def set_enable(self, *, on: bool) -> None:
        await self._apply_command(
            name='set_enable',
            target_preview=bool(on),
            deadline_s=2.0,
            satisfies=lambda st: bool(st.enabled) == bool(on),
            write_fn=lambda: (self.laser.enable() if on else self.laser.disable()),
        )

    async def set_power(self, *, power_mw: float) -> None:
        five_percent = 0.05 * float(power_mw)
        allowed_diff = min(five_percent, self._max_allowed_power_setpoint_diff)

        def set_power():
            self.laser.power_setpoint_mw = float(power_mw)

        await self._apply_command(
            name='set_power',
            target_preview=float(power_mw),
            deadline_s=2.0,
            satisfies=lambda st, tgt=float(power_mw), tol=allowed_diff: abs(st.power_setpoint - tgt) <= tol,
            write_fn=set_power,
        )

    def _read_state(self) -> LaserState:
        return LaserState(
            wavelength=int(self.laser.wavelength),
            enabled=self.laser.is_enabled,
            power_setpoint=self.laser.power_setpoint_mw,
            power=float(self.laser.power_mw),
            temperature=float(self.laser.temperature_c or 0.0),
        )

from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar, Protocol

from voxel.devices.device_agent import AgentEvent, DeviceState, VoxelDeviceAgent
from voxel.utils.descriptors.deliminated import DeliminatedFloat

from .base import VoxelLaser


class LaserState(DeviceState):
    wavelength: int
    enabled: bool
    power_setpoint: DeliminatedFloat
    power: float
    temperature: float
    model_config: ClassVar = {'arbitrary_types_allowed': True}  # if needed


class LaserAgentProtocol(Protocol):
    # Lifecycle
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # Commands (keep idempotent)
    async def set_enable(self, *, on: bool) -> None: ...
    async def set_power(self, *, power_mw: float) -> None: ...

    # Queries
    async def get_state(self) -> LaserState: ...

    # Streams
    def states(self) -> AsyncGenerator[LaserState]: ...
    def events(self) -> AsyncGenerator[AgentEvent]: ...


class LaserAgent(VoxelDeviceAgent[LaserState], LaserAgentProtocol):
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

        await self._apply_command(
            name='set_power',
            target_preview=float(power_mw),
            deadline_s=2.0,
            satisfies=lambda st, tgt=float(power_mw), tol=allowed_diff: abs(st.power_setpoint - tgt) <= tol,
            write_fn=lambda: setattr(self.laser, 'power_setpoint_mw', float(power_mw)),
        )

    def _is_laser_enabled(self) -> bool:
        # TODO: (@walter) add is_enabled to VoxelLaser
        setpoint = self.laser.power_setpoint_mw
        power = self.laser.power_mw
        diff_percent = (abs(setpoint - power) / setpoint * 100.0) if setpoint > 0 else 0.0
        return diff_percent < self._enabled_diff_percent

    def _read_state(self) -> LaserState:
        return LaserState(
            wavelength=int(self.laser.wavelength),
            enabled=self._is_laser_enabled(),
            power_setpoint=self.laser.power_setpoint_mw,
            power=float(self.laser.power_mw),
            temperature=float(self.laser.temperature_c or 0.0),
        )


class QtLaserAgentBridge(LaserAgent): ...

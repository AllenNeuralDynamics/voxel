"""Typed scan-controller handle backed by the shared device-property cache."""

import asyncio
import time

from pydantic import TypeAdapter
from rigup.device.handle import Adapter, DeviceProperty

from rigup import DeviceHandle
from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig

from .base import ScanController, StageStatus, XYPosition

_FLOAT_ADAPTER = TypeAdapter(float)
_POLL_INTERVAL_S = 0.05


class ScanControllerHandle(DeviceHandle[ScanController]):
    """Typed view of a scan controller: configure and run strip passes, move and home the stage, wait for motion to end."""

    def __init__(self, adapter: Adapter[ScanController]) -> None:
        super().__init__(adapter)
        self.is_running: DeviceProperty[bool] = self.props.property("is_running", bool)
        self.position_mm: DeviceProperty[XYPosition] = self.props.property("position_mm", XYPosition.model_validate)
        self.move_velocity_mm_s: DeviceProperty[float] = self.props.property(
            "move_velocity_mm_s", _FLOAT_ADAPTER.validate_python
        )
        self.motion_timeout_s: DeviceProperty[float] = self.props.property(
            "motion_timeout_s", _FLOAT_ADAPTER.validate_python
        )

    async def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        """Load the pass geometry and gating."""
        await self.call("configure", config, derived)

    async def run(self, direction: ScanDirection) -> None:
        """Start one strip pass in the given direction without blocking."""
        await self.call("run", direction)

    async def move_abs(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        """Start a move to an absolute (X, Y) position in mm; ``velocity_mm_s`` None uses the configured speed."""
        await self.call("move_abs", x_mm, y_mm, velocity_mm_s)

    async def move_rel(self, dx_mm: float, dy_mm: float) -> None:
        """Start a move by a relative (X, Y) step in mm."""
        await self.call("move_rel", dx_mm, dy_mm)

    async def go_home(self) -> None:
        """Start the move to the home position."""
        await self.call("go_home")

    async def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait, without blocking the loop, until passes and moves have ended; raise on timeout or an axis fault.

        ``timeout_s`` None: use the controller's ``motion_timeout_s``.
        """
        timeout_s = await self.motion_timeout_s.get() if timeout_s is None else timeout_s
        deadline = time.monotonic() + timeout_s
        while await self.is_running.get():
            if time.monotonic() > deadline:
                raise TimeoutError(f"Motion did not end within {timeout_s:g} s")
            await asyncio.sleep(_POLL_INTERVAL_S)
        status = await self.read_status()
        for name, axis in (("x", status.x), ("y", status.y)):  # a faulted axis stops, so check once the wait ends
            if axis.fault or axis.motor_error:
                raise RuntimeError(f"Axis {name} fault {axis.fault}, motor error {axis.motor_error}")

    async def read_status(self) -> StageStatus:
        """Per-axis motor state and faults."""
        return StageStatus.model_validate(await self.call("read_status"))

    async def abort(self) -> None:
        """Stop the pass and close every gate. Safe when idle."""
        await self.call("abort")

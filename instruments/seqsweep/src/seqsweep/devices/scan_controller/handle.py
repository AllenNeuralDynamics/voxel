"""Typed scan-controller handle backed by the shared device-property cache."""

from rigup.device.handle import Adapter, DeviceProperty

from rigup import DeviceHandle

from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig

from .base import ScanController


class ScanControllerHandle(DeviceHandle[ScanController]):
    """Typed view of a scan controller: load a pass, run it, abort it."""

    def __init__(self, adapter: Adapter[ScanController]) -> None:
        super().__init__(adapter)
        self.is_running: DeviceProperty[bool] = self.props.property("is_running", bool)

    async def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        """Load the pass geometry and gating."""
        await self.call("configure", config, derived)

    async def run(self, direction: ScanDirection) -> None:
        """Start one strip pass in the given direction without blocking."""
        await self.call("run", direction)

    async def move_to(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        """Start a move to an absolute (X, Y) position in mm; ``velocity_mm_s`` None uses the configured speed."""
        await self.call("move_to", x_mm, y_mm, velocity_mm_s)

    async def move_by(self, dx_mm: float, dy_mm: float) -> None:
        """Start a move by a relative (X, Y) step in mm."""
        await self.call("move_by", dx_mm, dy_mm)

    async def go_home(self) -> None:
        """Start a move to the configured origin."""
        await self.call("go_home")

    async def wait_motion_end(self) -> None:
        """Block until both axes have settled."""
        await self.call("wait_motion_end")

    async def read_status(self) -> dict[str, dict[str, float | bool | int]]:
        """Per-axis position, motor state and faults: ``{'x': {...}, 'y': {...}}``."""
        return await self.call("read_status")

    async def abort(self) -> None:
        """Stop the pass and close every gate. Safe when idle."""
        await self.call("abort")

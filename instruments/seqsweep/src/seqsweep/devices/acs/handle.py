"""Typed scan-controller handle backed by the shared device-property cache."""

from rigup.device.handle import Adapter, DeviceProperty

from rigup import DeviceHandle

from .base import ScanController, ScanDirection, ScanPassConfig


class ScanControllerHandle(DeviceHandle[ScanController]):
    """Typed view of a scan controller: load a pass, run it, abort it."""

    def __init__(self, adapter: Adapter[ScanController]) -> None:
        super().__init__(adapter)
        self.is_running: DeviceProperty[bool] = self.props.property("is_running", bool)

    async def configure(self, config: ScanPassConfig) -> None:
        """Load the pass geometry and gating."""
        await self.call("configure", config)

    async def run(self, direction: ScanDirection) -> None:
        """Start one strip pass in the given direction without blocking."""
        await self.call("run", direction)

    async def abort(self) -> None:
        """Stop the pass and close every gate. Safe when idle."""
        await self.call("abort")

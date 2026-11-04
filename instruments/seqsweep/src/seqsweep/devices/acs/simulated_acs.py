"""Simulated ACS scan controller: same API as the real controller, no hardware."""

from .base import ScanController, ScanDirection, ScanPassConfig


class SimulatedAcsController(ScanController):
    """Timer-only scan controller: a pass lasts its configured duration times ``time_scale``."""

    def __init__(self, uid: str, *, gate_outputs: dict[str, str], time_scale: float = 1.0) -> None:
        super().__init__(uid, gate_outputs=gate_outputs)
        self._time_scale = time_scale

    def configure(self, config: ScanPassConfig) -> None:
        # TODO: store the pass and its duration
        pass

    def run(self, direction: ScanDirection) -> None:
        # TODO: start a timer for duration * time_scale
        pass

    def abort(self) -> None:
        # TODO: clear the timer
        pass

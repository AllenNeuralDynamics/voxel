"""Simulated ACS scan controller: same API as the real controller, no hardware."""

import time

from seqsweep.job_model import DerivedScan, ScanDirection, ScanPassConfig

from .base import ScanController


class SimulatedScanController(ScanController):
    """Timer-only scan controller: a pass lasts its configured duration times ``time_scale``.

    Moves are instant: the stage position is tracked so the stage test calls give sensible answers,
    but there is no travel time and no limit check.
    """

    def __init__(
        self,
        uid: str,
        *,
        move_velocity_mm_s: float,
        motion_timeout_s: float = 60.0,
        time_scale: float = 1.0,
        home_mm: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        super().__init__(uid, move_velocity_mm_s=move_velocity_mm_s, motion_timeout_s=motion_timeout_s)
        self._time_scale = time_scale
        self._home_mm = home_mm
        self._x_mm, self._y_mm = home_mm

    @property
    def is_running(self) -> bool:
        return False  # run() blocks for the whole simulated pass, so nothing runs in the background

    def move_abs(self, x_mm: float, y_mm: float, velocity_mm_s: float | None = None) -> None:
        if velocity_mm_s is not None and velocity_mm_s <= 0:
            raise ValueError("velocity_mm_s must be positive")
        self._x_mm, self._y_mm = x_mm, y_mm

    def move_rel(self, dx_mm: float, dy_mm: float) -> None:
        self.move_abs(self._x_mm + dx_mm, self._y_mm + dy_mm)

    def go_home(self) -> None:
        self._x_mm, self._y_mm = self._home_mm

    def read_status(self) -> dict[str, dict[str, float | bool | int]]:
        return {
            axis: {
                "position_mm": position_mm,
                "enabled": True,
                "in_position": True,
                "moving": False,
                "accelerating": False,
                "fault": 0,
                "motor_error": 0,
            }
            for axis, position_mm in (("x", self._x_mm), ("y", self._y_mm))
        }

    def configure(self, config: ScanPassConfig, derived: DerivedScan) -> None:
        # TODO: store the pass and its duration
        pass

    def run(self, direction: ScanDirection) -> None:
        # TODO: start a timer for duration * time_scale
        self.log.info("Running scan in direction: %s", direction)
        time.sleep(1)
        self.log.info("Scan completed.")

    def abort(self) -> None:
        # TODO: clear the timer
        pass

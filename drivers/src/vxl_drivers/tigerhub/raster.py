"""A raster scan on 1 Tiger card, in µm: a fast axis that sweeps with pulses, and a slow axis that steps between lines.

https://docs.asiimaging.com/commands/scan, https://docs.asiimaging.com/commands/scanr,
https://docs.asiimaging.com/commands/scanv
"""

from vxl_drivers.tigerhub.box import TigerBox
from vxl_drivers.tigerhub.ops.scan import ScanPattern, ScanRConfig, ScanVConfig

UM_PER_MM = 1000.0


class TigerRasterScan:
    """A raster scan of ``fast_axis`` and ``slow_axis``, given by their letters, on the same card of ``box``. Program
    both axes, then :meth:`start`. ``pattern`` is raster (every line the same way) or serpentine (back and forth)."""

    def __init__(
        self, box: TigerBox, *, fast_axis: str, slow_axis: str, pattern: ScanPattern = ScanPattern.RASTER
    ) -> None:
        self._box = box
        box.setup_scanrv(fast_axis=fast_axis, slow_axis=slow_axis, pattern=pattern)

    def configure_fast(
        self, start_um: float, stop_um: float, pulse_interval_um: float, retrace_percent: int | None = 67
    ) -> float:
        """Program the fast axis's line: from ``start_um`` to ``stop_um``, 1 pulse every ``pulse_interval_um``, and back
        at ``retrace_percent`` of its top speed. Give back the pulse interval the hardware will really use, rounded to
        whole encoder counts."""
        return self._box.configure_scan_r(
            ScanRConfig(
                start_mm=start_um / UM_PER_MM,
                stop_mm=stop_um / UM_PER_MM,
                pulse_interval_um=pulse_interval_um,
                retrace_speed_percent=retrace_percent,
            )
        )

    def configure_slow(
        self,
        start_um: float,
        stop_um: float,
        line_count: int,
        *,
        overshoot_time_ms: int | None = None,
        overshoot_factor: float | None = None,
    ) -> None:
        """Program the slow axis: ``line_count`` lines from ``start_um`` to ``stop_um``. ``overshoot_time_ms`` adds
        settling time before each line, and ``overshoot_factor`` scales the backlash overshoot."""
        self._box.configure_scan_v(
            ScanVConfig(
                start_mm=start_um / UM_PER_MM,
                stop_mm=stop_um / UM_PER_MM,
                line_count=line_count,
                overshoot_time_ms=overshoot_time_ms,
                overshoot_factor=overshoot_factor,
            )
        )

    def start(self) -> None:
        self._box.start_scan()

    def stop(self) -> None:
        self._box.stop_scan()


__all__ = ["TigerRasterScan"]

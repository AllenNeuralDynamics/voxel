"""The XYZ stage and the Tiger raster scan, against simulated axes and a fake controller."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest
from rich.console import Console
from vxl_drivers.axes.tiger_stage import XYZStage, _PositionWidget
from vxl_drivers.tigerhub.ops.scan import ScanPattern, ScanRConfig, ScanVConfig
from vxl_drivers.tigerhub.raster import TigerRasterScan

from vxl.devices.axes.continuous.simulated import SimulatedLinearAxis

if TYPE_CHECKING:
    from vxl_drivers.tigerhub.box import TigerBox


@dataclass
class _FakeBox:
    calls: list[tuple[str, Any]] = field(default_factory=list)

    def setup_scanrv(self, *, fast_axis: str, slow_axis: str, pattern: ScanPattern) -> None:
        self.calls.append(("setup_scanrv", (fast_axis, slow_axis, pattern)))

    def configure_scan_r(self, cfg: ScanRConfig) -> float:
        self.calls.append(("configure_scan_r", cfg))
        return 1.25

    def configure_scan_v(self, cfg: ScanVConfig) -> None:
        self.calls.append(("configure_scan_v", cfg))

    def start_scan(self) -> None:
        self.calls.append(("start_scan", None))

    def stop_scan(self) -> None:
        self.calls.append(("stop_scan", None))


def test_a_raster_scan_programs_both_axes_in_millimetres_and_runs() -> None:
    box = _FakeBox()
    scan = TigerRasterScan(cast("TigerBox", box), fast_axis="X", slow_axis="Y", pattern=ScanPattern.SERPENTINE)

    assert scan.configure_fast(0.0, 500.0, 1.2) == pytest.approx(1.25)
    scan.configure_slow(0.0, 200.0, 5)
    scan.start()
    scan.stop()

    names = [name for name, _ in box.calls]
    assert names == ["setup_scanrv", "configure_scan_r", "configure_scan_v", "start_scan", "stop_scan"]
    assert box.calls[0][1] == ("X", "Y", ScanPattern.SERPENTINE)
    fast, slow = box.calls[1][1], box.calls[2][1]
    assert (fast.start_mm, fast.stop_mm, fast.pulse_interval_um) == (0.0, pytest.approx(0.5), 1.2)
    assert (slow.stop_mm, slow.line_count) == (pytest.approx(0.2), 5)


def test_an_xyz_stage_moves_its_3_axes_together_and_waits_until_still() -> None:
    axes = [SimulatedLinearAxis(name, speed=100_000) for name in ("x", "y", "z")]
    stage = XYZStage(*axes)

    stage.move_to(10.0, 20.0, 30.0, wait=True, timeout_s=2)

    assert stage.position == (pytest.approx(10.0), pytest.approx(20.0), pytest.approx(30.0))


def test_the_position_widget_draws_the_stage() -> None:
    console = Console(record=True, width=120)
    console.print(_PositionWidget(10.0, 20.0, 5.0, grid_width=20, grid_height=10))
    text = console.export_text()
    assert "XY Position" in text
    assert "10.00" in text

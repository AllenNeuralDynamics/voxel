# This is experimental for possible implementation in spim_rig if needed.

from abc import ABC, abstractmethod
from dataclasses import dataclass

from spim_drivers.axes.asi import TigerLinearAxis
from spim_drivers.tigerhub.hub import TigerHub
from spim_drivers.tigerhub.ops.scan import ScanPattern, ScanRConfig, ScanVConfig
from spim_rig.axes.continuous.base import ContinuousAxis, TTLStepper


class XYZStage[A: ContinuousAxis]:
    def __init__(self, x: A, y: A, z: A) -> None:
        self.x = x
        self.y = y
        self.z = z

    def move_abs(self, x: float, y: float, z: float, *, wait: bool = False) -> None:
        self.x.move_abs(x, wait=False)
        self.y.move_abs(y, wait=False)
        self.z.move_abs(z, wait=wait)

    @property
    def position(self) -> tuple[float, float, float]:
        return self.x.position, self.y.position, self.z.position

    def get_ttl_stepper(self) -> TTLStepper:
        if (stepper := self.z.get_ttl_stepper()) is not None:
            return stepper
        raise ValueError("Unable to validate TTL Stepper support on scanning axis (Z)")


@dataclass(frozen=True)
class FastAxisConfig:
    start_mm: float
    stop_mm: float
    pulse_interval_um: float
    retrace_speed_percent: int | None = 67


@dataclass(frozen=True)
class SlowAxisConfig:
    start_mm: float
    stop_mm: float
    line_count: int
    overshoot_time_ms: int | None = None
    overshoot_factor: float | None = None


class ScanSession(ABC):
    @abstractmethod
    def configure_fast_axis(self, fast_cfg: FastAxisConfig): ...

    @abstractmethod
    def configure_slow_axis(self, slow_cfg: SlowAxisConfig): ...

    @abstractmethod
    def start(self): ...

    @abstractmethod
    def stop(self): ...


class ScannableStage[A: ContinuousAxis](ABC, XYZStage[A]):
    @abstractmethod
    def new_scan_session(self, pattern: ScanPattern = ScanPattern.RASTER) -> ScanSession: ...


class TigerScanSession(ScanSession):
    def __init__(self, fast: TigerLinearAxis, slow: TigerLinearAxis, pattern: ScanPattern = ScanPattern.RASTER):
        if fast.hub != slow.hub:
            raise ValueError("Fast and slow axes must be on the same TigerHub instance.")
        self.fast = fast
        self.slow = slow
        self.hub = fast.hub
        self._pattern = pattern
        self.hub.box.setup_scanrv(fast_axis=self.fast.asi_label, slow_axis=self.slow.asi_label, pattern=pattern)

    def configure_fast_axis(self, fast_cfg: FastAxisConfig):
        self.hub.box.configure_scan_r(
            ScanRConfig(
                start_mm=fast_cfg.start_mm,
                pulse_interval_um=fast_cfg.pulse_interval_um,
                stop_mm=fast_cfg.stop_mm,
                retrace_speed_percent=fast_cfg.retrace_speed_percent,
            )
        )

    def configure_slow_axis(self, slow_cfg: SlowAxisConfig):
        self.hub.box.configure_scan_v(
            ScanVConfig(
                start_mm=slow_cfg.start_mm,
                stop_mm=slow_cfg.stop_mm,
                line_count=slow_cfg.line_count,
                overshoot_time_ms=slow_cfg.overshoot_time_ms,
                overshoot_factor=slow_cfg.overshoot_factor,
            )
        )

    def start(self):
        self.hub.box.start_scan()

    def stop(self):
        self.hub.box.stop_scan()


class TigerXYZStage(ScannableStage[TigerLinearAxis]):
    def __init__(self, x: TigerLinearAxis, y: TigerLinearAxis, z: TigerLinearAxis):
        super().__init__(x, y, z)

    def new_scan_session(self, pattern: ScanPattern = ScanPattern.RASTER) -> TigerScanSession:
        return TigerScanSession(fast=self.x, slow=self.y, pattern=pattern)


if __name__ == "__main__":
    import time

    from rich.box import HEAVY, ROUNDED
    from rich.console import Console, ConsoleOptions
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    class XYZStageWidget:
        """A Rich renderable widget to display the XYZ position of a stage."""

        def __init__(
            self,
            x: float = 0.0,
            y: float = 0.0,
            z: float = 0.0,
            x_limits: tuple[float, float] = (0.0, 100.0),
            y_limits: tuple[float, float] = (0.0, 100.0),
            z_limits: tuple[float, float] = (0.0, 50.0),
            grid_width: int = 40,
            grid_height: int = 20,
        ):
            self.x, self.y, self.z = x, y, z
            self.x_limits = x_limits
            self.y_limits = y_limits
            self.z_limits = z_limits
            self.grid_width = grid_width
            self.grid_height = grid_height

        def _map_value(self, value: float, limits: tuple[float, float], size: int) -> int:
            """Maps a real-world coordinate to a discrete grid coordinate."""
            min_val, max_val = limits
            if max_val == min_val:
                return 0
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(size - 1, int(normalized * size)))

        def _build_xy_panel(self) -> Panel:
            """Builds the XY grid Panel."""
            grid_x = self._map_value(self.x, self.x_limits, self.grid_width)
            grid_y = self.grid_height - 1 - self._map_value(self.y, self.y_limits, self.grid_height)

            grid = [[" " for _ in range(self.grid_width)] for _ in range(self.grid_height)]

            for i in range(self.grid_width):
                grid[grid_y][i] = "─"
            for i in range(self.grid_height):
                grid[i][grid_x] = "│"
            grid[grid_y][grid_x] = "┼"

            canvas = Text("\n".join("".join(row) for row in grid), style="bold yellow")
            subtitle = f"[green]X:[/] {self.x:6.2f}  [green]Y:[/] {self.y:6.2f}"

            return Panel(
                canvas,
                title="[bold cyan]XY Position[/]",
                subtitle=subtitle,
                border_style="blue",
                box=HEAVY,
                height=self.grid_height + 2,
            )

        def _build_z_panel(self) -> Panel:
            """Builds the Z slider Panel."""
            slider_height = self.grid_height
            slider_pos = slider_height - 1 - self._map_value(self.z, self.z_limits, slider_height)

            slider_chars = ["│"] * slider_height
            slider_chars[slider_pos] = "█"

            canvas = Text("\n".join(slider_chars), style="bold magenta")
            subtitle = f"[green]Z:[/] {self.z:6.2f}"

            return Panel(
                canvas,
                title="[bold cyan]Z[/]",
                subtitle=subtitle,
                border_style="blue",
                box=ROUNDED,
                width=7,
                height=self.grid_height + 2,
            )

        def __rich_console__(self, console: Console, options: ConsoleOptions):
            """This method is called by Rich to render the complete widget."""
            layout_table = Table.grid(padding=(0, 1))
            layout_table.add_column()
            layout_table.add_column()

            # Create a subtitle for the whole widget showing the limits
            details_text = (
                f"Limits: [cyan]X:[/] {self.x_limits}  [cyan]Y:[/] {self.y_limits}  [cyan]Z:[/] {self.z_limits}  "
                f"[cyan]Pos:[/] ({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"
            )

            # The main layout is a table with the panels and a title row
            main_view = Table.grid(padding=0)
            main_view.add_row(layout_table)
            main_view.add_row(Text.from_markup(details_text, justify="center", style="dim"))

            layout_table.add_row(self._build_xy_panel(), self._build_z_panel())
            yield main_view

    console = Console()
    PORT = "COM3"
    hub = TigerHub(PORT)

    x_axis = TigerLinearAxis(hub=hub, uid="x-axis", axis_label="X")
    y_axis = TigerLinearAxis(hub=hub, uid="y-axis", axis_label="Y")
    z_axis = TigerLinearAxis(hub=hub, uid="z-axis", axis_label="Z")

    stage = TigerXYZStage(x_axis, y_axis, z_axis)

    z_pos = z_axis.position
    z_min = z_pos - 0.5
    z_max = z_pos + 0.5

    widget = XYZStageWidget(
        x=stage.x.position,
        y=stage.y.position,
        z=z_pos,
        x_limits=(-50.0, -5.0),
        y_limits=(-0.0, 50.0),
        z_limits=(z_min, z_max),
        grid_width=80,
        grid_height=40,
    )

    console.print(f"X limits: {x_axis.lower_limit} - {x_axis.upper_limit}")
    console.print(f"Y limits: {y_axis.lower_limit} - {y_axis.upper_limit}")
    console.print(f"Z limits: {z_axis.lower_limit} - {z_axis.upper_limit}")

    with Live(renderable=widget, console=console, refresh_per_second=2, screen=True) as live:
        live.console.print("[bold green]Starting XY stage simulation...[/]", justify="center")
        time.sleep(1)
        while True:
            try:
                pos = stage.position
                widget.x = pos[0]
                widget.y = pos[1]
                widget.z = pos[2]
                time.sleep(0.5)
            except KeyboardInterrupt:
                break

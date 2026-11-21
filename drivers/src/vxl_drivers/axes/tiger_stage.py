"""3 linear axes as an XYZ stage, and on Tiger axes, an X/Y raster scan. Run it to watch a Tiger stage's position:
``uv run python -m vxl_drivers.axes.tiger_stage --port COM3``."""

import argparse
import time

from rich.box import HEAVY, ROUNDED
from rich.console import Console, ConsoleOptions
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from vxl_drivers.axes.asi import TigerLinearAxis
from vxl_drivers.tigerhub.hub import TigerHub
from vxl_drivers.tigerhub.ops.scan import ScanPattern
from vxl_drivers.tigerhub.raster import TigerRasterScan

from vxl.devices.axes.continuous.linear import LinearAxis

_POLL_S = 0.01


class XYZStage[A: LinearAxis]:
    """3 linear axes, ``x``, ``y`` and ``z``, moved and read together, in µm."""

    def __init__(self, x: A, y: A, z: A) -> None:
        self.x, self.y, self.z = x, y, z

    def move_to(self, x: float, y: float, z: float, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Start all 3 moves, and with ``wait``, wait until the stage is still."""
        for axis, position in ((self.x, x), (self.y, y), (self.z, z)):
            axis.move_to(position)
        if wait:
            self.wait_until_still(timeout_s)

    def wait_until_still(self, timeout_s: float | None = None) -> None:
        """Wait until no axis moves. Raise ``TimeoutError`` after ``timeout_s``."""
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        while any(axis.is_moving for axis in (self.x, self.y, self.z)):
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"the stage still moves after {timeout_s} s")
            time.sleep(_POLL_S)

    @property
    def position(self) -> tuple[float, float, float]:
        return self.x.position, self.y.position, self.z.position


class TigerXYZStage(XYZStage[TigerLinearAxis]):
    """An XYZ stage of Tiger axes. X and Y must be on the same card for :meth:`raster_scan`."""

    def raster_scan(self, pattern: ScanPattern = ScanPattern.RASTER) -> TigerRasterScan:
        """A raster scan with X as the fast axis and Y as the slow one."""
        if self.x.hub is not self.y.hub:
            raise ValueError("X and Y must be on the same Tiger hub to raster scan")
        return TigerRasterScan(self.x.hub.box, fast_axis=self.x.label, slow_axis=self.y.label, pattern=pattern)


class _PositionWidget:
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


def main() -> None:
    """Show a Tiger stage's position live until Ctrl-C."""
    parser = argparse.ArgumentParser(description="Watch the position of a Tiger XYZ stage")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--axes", default="XYZ", help="the controller's letters for X, Y and Z")
    args = parser.parse_args()
    console = Console()
    hub = TigerHub(args.port)
    x, y, z = (
        TigerLinearAxis(f"{name}_axis", hub=hub, axis_label=letter)
        for name, letter in zip("xyz", args.axes, strict=True)
    )
    stage = TigerXYZStage(x, y, z)
    try:
        widget = _PositionWidget(
            *stage.position,
            x_limits=(x.limits.low, x.limits.high),
            y_limits=(y.limits.low, y.limits.high),
            z_limits=(z.limits.low, z.limits.high),
            grid_width=80,
            grid_height=40,
        )
        with Live(renderable=widget, console=console, refresh_per_second=2, screen=True):
            while True:
                widget.x, widget.y, widget.z = stage.position
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for axis in (x, y, z):
            axis.dispose()
        hub.dispose()


if __name__ == "__main__":
    main()


__all__ = ["TigerXYZStage", "XYZStage"]

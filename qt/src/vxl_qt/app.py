"""The Voxel Qt windows.

Two top-level windows, IDE-style:

- :class:`LaunchWindow` — the home: owns the core :class:`vxl.app.VoxelApp` (and thus the instrument
  lifecycle), lists the instruments, and on launch spawns the control window and hides itself,
  reappearing when that window closes.
- :class:`MainWindow` — the control workspace for one launched instrument (the app's main window):
  owns the instrument-scoped hardware stores + panels, built per launch and torn down on close.

There is no stacked-pages/phase machinery — each window simply exists in its own mode. Pages/panels
bind to the instrument's reactive primitives (``state``, ``active_profile_id``) directly.

:func:`main` is the CLI entry point: it builds the Qt app, starts the qasync event loop, and shows
the :class:`LaunchWindow`.
"""

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import qasync
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent, QColor, QEnterEvent, QIcon, QMouseEvent, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from vxl.app import InstrumentInfo, VoxelApp
from vxl.instrument import Instrument
from vxl_qt.devices import DevicesStore
from vxl_qt.devices.stage import StageStore
from vxl_qt.preview import PreviewPanel
from vxl_qt.preview.models import PreviewStore
from vxl_qt.ui.assets import VOXEL_LOGO, load_fonts
from vxl_qt.ui.kit import (
    Button,
    Color,
    Colors,
    Flex,
    FontSize,
    Separator,
    Size,
    Spacing,
    Splitter,
    Stretch,
    Text,
    ToolButton,
    app_stylesheet,
    vbox,
)
from vxlib import Teardown, configure_logging, fire_and_forget

from .channels import ChannelsPanel
from .grid import GridCanvas, StageControls, TasksTable
from .logs import LogPanel
from .waveforms import WaveformsPanel

log = logging.getLogger(__name__)


class PlaceholderPanel(QWidget):
    """Placeholder panel for features not yet implemented."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        layout = vbox(self)

        label = Text.muted(title, color=Colors.TEXT_DISABLED)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class TabButton(QWidget):
    """A single tab in the bottom tab bar."""

    def __init__(self, label: str, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self._selected = False
        self._label = Text.muted(label)
        self._label.setStyleSheet("padding: 6px 12px; border-top: 2px solid transparent;")
        vbox(self, margins=(0, 0, 0, 0)).addWidget(self._label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def index(self) -> int:
        return self._index

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        border = Colors.ACCENT if selected else "transparent"
        color = Colors.ACCENT if selected else Colors.TEXT_MUTED
        self._label.setStyleSheet(f"color: {color}; padding: 6px 12px; border-top: 2px solid {border};")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        del event
        parent = self.parent()
        while parent is not None and not isinstance(parent, TabbedPanel):
            parent = parent.parent()
        if isinstance(parent, TabbedPanel):
            parent.set_current_index(self._index)

    def enterEvent(self, event: QEnterEvent) -> None:
        del event
        if not self._selected:
            self._label.setStyleSheet(f"color: {Colors.TEXT}; padding: 6px 12px; border-top: 2px solid transparent;")

    def leaveEvent(self, event: QEvent) -> None:
        del event
        if not self._selected:
            self.set_selected(False)  # restore the unselected style


class TabbedPanel(QWidget):
    """A stacked content area with a bottom tab bar and an inline status-widget slot on the right."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabs: list[TabButton] = []
        self._current_index = 0
        self._stack = QStackedWidget()
        self._tab_bar = Flex.hstack(spacing=0)
        self._status = Flex.hstack(spacing=Spacing.MD)
        bottom = Flex.hstack(self._tab_bar, Stretch(), self._status, spacing=0, padding=(0, 0, Spacing.LG, 0))
        layout = vbox(self, spacing=0)
        layout.addWidget(self._stack, stretch=1)
        layout.addWidget(Separator())
        layout.addWidget(bottom)

    def add_tab(self, widget: QWidget, label: str) -> None:
        index = len(self._tabs)
        tab = TabButton(label, index)
        self._tabs.append(tab)
        self._tab_bar.add(tab)
        self._stack.addWidget(widget)
        if index == 0:
            tab.set_selected(True)

    def set_status_widget(self, widget: QWidget) -> None:
        self._status.add(widget)

    def set_current_index(self, index: int) -> None:
        if not 0 <= index < len(self._tabs):
            return
        if 0 <= self._current_index < len(self._tabs):
            self._tabs[self._current_index].set_selected(False)
        self._current_index = index
        self._tabs[index].set_selected(True)
        self._stack.setCurrentIndex(index)


class Footer(QWidget):
    """Stage position + per-laser indicators, shown inline with the tab bar. Binds to the device and
    stage stores directly (no app/coordinator)."""

    def __init__(self, devices: DevicesStore, stage: StageStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._devices = devices
        self._stage = stage
        self.setFixedHeight(Size.XL)
        self._stage_label = Text.value("X: 0.000  Y: 0.000  Z: 0.000", color=Colors.TEXT_MUTED)
        self._laser_box = Flex.hstack(spacing=Spacing.XS)
        self._indicators: dict[str, Text] = {}
        content = Flex.hstack(
            self._stage_label, self._laser_box, spacing=Spacing.LG, padding=(Spacing.MD, 0, Spacing.MD, 0)
        )
        vbox(self, margins=(0, 0, 0, 0)).addWidget(content)
        devices.ready.connect(self._on_devices_ready)
        stage.position_changed.connect(self._on_position)

    def _on_devices_ready(self) -> None:
        self._laser_box.clear()
        self._indicators.clear()
        for uid, adapter in self._devices.get_lasers().items():
            dot = Text.default("●", color=Colors.TEXT_DISABLED, size=FontSize.XS)
            self._laser_box.add(dot)
            self._indicators[uid] = dot
            adapter.properties_changed.connect(lambda props, u=uid: self._on_laser_props(u, props))
            adapter.request_initial_properties()

    def _on_laser_props(self, uid: str, props: dict[str, Any]) -> None:
        dot = self._indicators.get(uid)
        if dot is None:
            return
        if "wavelength" in props:
            dot.setToolTip(f"{int(props['wavelength'])}nm")
        if "is_enabled" in props:
            wavelength = self._devices.get_property(uid, "wavelength")
            color = (
                Color.from_wavelength(int(wavelength)) if props["is_enabled"] and wavelength else Colors.TEXT_DISABLED
            )
            dot.fmt = dot.fmt.with_(color=color)

    def _on_position(self) -> None:
        s = self._stage
        self._stage_label.setText(f"X: {s.x.position:.3f}  Y: {s.y.position:.3f}  Z: {s.z.position:.3f}")


class MainWindow(QMainWindow):
    """The control workspace for a launched instrument — the app's main window.

    Owns the instrument-scoped hardware stores and the panels (their lifetime is this window's).
    Constructed synchronously; ``start()`` brings the stores up. Closing the window tears everything
    down and calls ``on_closed`` (the launcher then closes the instrument and comes back home).
    """

    def __init__(
        self,
        instrument: Instrument,
        on_closed: Callable[[], Awaitable[None]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._on_closed = on_closed
        self._devices = DevicesStore(parent=self)
        self._preview = PreviewStore(parent=self)
        self._stage = StageStore(parent=self)
        self._channels: ChannelsPanel | None = None
        self._tasks: TasksTable | None = None
        self._grid_canvas: GridCanvas | None = None
        self._stage_controls: StageControls | None = None
        self._unsubs: list[Teardown] = []

        self.setWindowTitle(f"Voxel — {instrument.path.stem}")
        self.setMinimumSize(1280, 800)
        self.setStyleSheet(f"QMainWindow {{ background-color: {Colors.BG_DARK}; }}")

        central = QWidget()
        root = vbox(central, spacing=Spacing.SM, margins=(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM))
        home = ToolButton("mdi6.home", color=Colors.TEXT_MUTED, color_hover=Colors.TEXT)
        home.setToolTip("Close instrument and return to the launcher")
        home.clicked.connect(self.close)  # -> closeEvent -> _shutdown -> on_closed (launcher returns)
        root.addWidget(Flex.hstack(home, Text.title(instrument.path.stem), Stretch(), spacing=Spacing.MD))
        root.addWidget(self._build_workspace(), stretch=1)
        self.setCentralWidget(central)

    def _build_workspace(self) -> QWidget:
        """Sidebar (channels) | center [preview · grid] over tabs [tasks · waveforms · logs] + footer.

        All panels bind directly to the instrument's reactive state; channels/preview/grid/tasks/
        waveforms/logs/footer are live.
        """
        content = Splitter(Qt.Orientation.Horizontal)
        self._channels = ChannelsPanel(self._instrument, self._devices)
        self._stage_controls = StageControls(self._instrument, self._devices)
        sidebar = QWidget()
        sidebar_layout = vbox(sidebar, spacing=Spacing.SM)
        sidebar_layout.addWidget(self._channels, stretch=1)  # channels fill, stage controls pinned to the bottom
        sidebar_layout.addWidget(self._stage_controls)
        content.addWidget(sidebar)

        center = Splitter(Qt.Orientation.Vertical)
        top = Splitter(Qt.Orientation.Horizontal)
        preview_panel = PreviewPanel(self._preview)
        # Feed viewport pan/zoom back to the cameras so they reprocess (and, later, tile) that region.
        preview_panel.viewport_changed.connect(lambda *_: self._instrument.update_viewport(self._preview.viewport))
        top.addWidget(preview_panel)
        self._grid_canvas = GridCanvas(self._instrument, self._stage)
        top.addWidget(self._grid_canvas)
        top.setSizes([500, 500])
        center.addWidget(top)

        tabs = TabbedPanel()
        self._tasks = TasksTable(self._instrument)
        tabs.add_tab(self._tasks, "Tasks")
        tabs.add_tab(WaveformsPanel(), "Waveforms")
        tabs.add_tab(LogPanel(), "Logs")
        tabs.set_status_widget(Footer(self._devices, self._stage))
        center.addWidget(tabs)
        center.setSizes([600, 400])

        content.addWidget(center)
        content.setSizes([320, 1080])
        return content

    async def start(self) -> None:
        """Bring the hardware stores up against the instrument (adapters start here)."""
        await self._devices.start(self._instrument.hal)
        cfg = self._instrument.hal.config.stage
        x, y, z = self._devices.get_adapter(cfg.x), self._devices.get_adapter(cfg.y), self._devices.get_adapter(cfg.z)
        if x and y and z:
            self._stage.bind(x, y, z)
        self._unsubs.append(self._preview.start_feed(self._instrument))

    def closeEvent(self, event: QCloseEvent) -> None:
        # Let the window close now; tear down stores and hand control back to the launcher async.
        fire_and_forget(self._shutdown(), log=log)
        event.accept()

    async def _shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        if self._channels is not None:
            self._channels.teardown()
            self._channels = None
        if self._tasks is not None:
            self._tasks.teardown()
            self._tasks = None
        if self._grid_canvas is not None:
            self._grid_canvas.teardown()
            self._grid_canvas = None
        if self._stage_controls is not None:
            self._stage_controls.teardown()
            self._stage_controls = None
        await self._devices.stop()
        self._preview.reset()
        self._stage.unbind()
        await self._on_closed()


class LaunchWindow(QWidget):
    """The home window: lists instruments and launches one (spawning the control window and hiding
    itself; reappears when that window closes), and scaffolds new instruments from the shipped
    templates. Owns the core app + the instrument lifecycle."""

    def __init__(self) -> None:
        super().__init__()
        self._core = VoxelApp()
        self._control: MainWindow | None = None

        self.setWindowTitle("Voxel — Instruments")
        self.resize(480, 560)
        self.setStyleSheet(f"background-color: {Colors.BG_DARK};")

        self._list = Flex.vstack(spacing=Spacing.SM)
        self._templates = Flex.vstack(spacing=Spacing.SM)
        self._status = Text.muted("")
        root = vbox(self, spacing=Spacing.LG, margins=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL))
        root.addWidget(Text.heading("Instruments"))
        root.addWidget(self._list)
        root.addWidget(Separator())
        root.addWidget(Text.heading("Create from template"))
        root.addWidget(self._templates)
        root.addWidget(self._status)
        root.addStretch(1)
        self._refresh()

    def _refresh(self) -> None:
        discovered = self._core.discover()
        self._list.clear()
        if not discovered.instruments:
            self._list.add(Text.muted("No instruments yet — launch one from a template below."))
        else:
            for name, info in discovered.instruments.items():
                self._list.add(self._row(name, info))

        self._templates.clear()
        if not discovered.templates:
            self._templates.add(Text.muted("No templates available."))
        else:
            for name in discovered.templates:
                self._templates.add(self._template_row(name))

    def _row(self, name: str, info: InstrumentInfo) -> QWidget:
        launch = Button("Launch")
        launch.setEnabled(info.ok)
        launch.clicked.connect(lambda: self._launch(name))
        label = Text.default(name) if info.ok else Text.default(f"{name} — invalid config", color=Colors.TEXT_MUTED)
        return Flex.hstack(label, Stretch(), launch, spacing=Spacing.MD)

    def _template_row(self, template: str) -> QWidget:
        launch = Button("Launch")
        launch.clicked.connect(lambda: self._launch_template(template))
        return Flex.hstack(Text.default(template), Stretch(), launch, spacing=Spacing.MD)

    def _launch(self, name: str) -> None:
        fire_and_forget(self._open(self._core.launch(name), name), log=log)

    def _launch_template(self, template: str) -> None:
        """Create an instrument from the template (named after it), then open it."""
        fire_and_forget(self._open(self._core.launch_template(template), template), log=log)

    async def _open(self, opening: Awaitable[Instrument], label: str) -> None:
        """Await `opening` (a launch or create+launch), spawn the control window, and hide home."""
        self._set_launching(True, label)
        try:
            instrument = await opening
            self._control = MainWindow(instrument, on_closed=self._on_control_closed)
            await self._control.start()
            self._control.showMaximized()
            self.hide()
        except FileExistsError:
            self._status.setText(f"An instrument named '{label}' already exists.")
            self._refresh()
        except Exception:
            log.exception("Failed to launch '%s'", label)
            self._status.setText(f"Failed to launch '{label}'.")
            if self._core.active.value is not None:
                await self._core.close()
            self._control = None
            self._refresh()
        finally:
            self._set_launching(False)

    async def _on_control_closed(self) -> None:
        """The control window closed (its stores already torn down): close the instrument, refresh,
        and come back home."""
        if self._core.active.value is not None:
            await self._core.close()
        self._control = None
        self._refresh()
        self.show()

    def _set_launching(self, launching: bool, name: str = "") -> None:
        self._status.setText(f"Launching {name}…" if launching else "")
        self.setEnabled(not launching)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Closing the home window quits the app (the control window, when open, returns here instead).
        if (app := QApplication.instance()) is not None:
            app.quit()
        event.accept()


# ============================== Entry point ==============================


def create_qapp() -> QApplication:
    """Create and configure the Qt application (style, palette, fonts, icon)."""
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setApplicationName("Voxel")
    qapp.setWindowIcon(QIcon(str(VOXEL_LOGO)))
    # The control window closing returns to the (hidden) launcher, so don't let Qt auto-quit when the
    # last visible window closes — only the launcher's own close quits the app (it calls app.quit()).
    qapp.setQuitOnLastWindowClosed(False)

    load_fonts()  # must be done after QApplication is created

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(Colors.BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(Colors.BG_LIGHT))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Colors.BG_MEDIUM))
    palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(Colors.BORDER))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Colors.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Colors.TEXT_BRIGHT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Colors.BG_MEDIUM))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT_BRIGHT))
    qapp.setPalette(palette)
    qapp.setStyleSheet(app_stylesheet())
    return qapp


def run_app(_config_path: Path | None = None) -> int:
    """Run the Voxel application with the qasync event loop. Returns the process exit code."""
    configure_logging(logging.INFO)
    qapp = create_qapp()
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    try:
        with loop:
            window = LaunchWindow()  # kept in scope so it isn't garbage-collected during run_forever
            window.show()
            log.info("Voxel application started")
            loop.run_forever()
    except KeyboardInterrupt:
        log.info("Application interrupted")
    except Exception:
        log.exception("Application error")
        return 1
    return 0


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Voxel - Microscope control application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("config", nargs="?", type=Path, help="Path to rig configuration YAML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        configure_logging(logging.DEBUG)

    sys.exit(run_app(args.config))


if __name__ == "__main__":
    main()

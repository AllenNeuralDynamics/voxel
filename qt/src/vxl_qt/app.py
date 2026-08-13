"""The Voxel Qt windows.

Two top-level windows, IDE-style:

- :class:`LaunchWindow` — the home: owns the live :class:`vxl.station.Station` and template source,
  lists instruments, and holds one scoped Instrument lease for the control window's lifetime.
- :class:`MainWindow` — the control workspace for one launched instrument (the app's main window):
  owns the instrument-scoped hardware stores + panels, built per launch and torn down on close.

There is no stacked-pages/phase machinery — each window simply exists in its own mode. Pages/panels
bind to the instrument's reactive primitives (``state``, ``active_profile_id``) directly.

:func:`main` is the CLI entry point: it builds the Qt app, starts the qasync event loop, and shows
the :class:`LaunchWindow`.
"""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import qasync
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent, QColor, QEnterEvent, QIcon, QMouseEvent, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget

from vxl.instrument import Instrument
from vxl.instrument.bench import InstrumentInspection
from vxl.station import InstrumentTemplates, SessionInfo, SessionState, Station, StationFeedConnection, StationFeedView
from vxl.system import StationConfig, load_voxel_env
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
            adapter.replay_cached_properties()

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
        station: Station,
        session: SessionInfo,
        on_closed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._station = station
        self._session = session
        self._on_closed = on_closed
        self._devices = DevicesStore(parent=self)
        self._preview = PreviewStore(parent=self)
        self._stage = StageStore(parent=self)
        self._channels: ChannelsPanel | None = None
        self._tasks: TasksTable | None = None
        self._grid_canvas: GridCanvas | None = None
        self._stage_controls: StageControls | None = None
        self._logs: LogPanel | None = None
        self._unsubs: list[Teardown] = []
        self._feed_task: asyncio.Task[None] | None = None
        self._shutdown_task: asyncio.Task[None] | None = None

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
        self._logs = LogPanel()
        tabs.add_tab(self._logs, "Logs")
        tabs.set_status_widget(Footer(self._devices, self._stage))
        center.addWidget(tabs)
        center.setSizes([600, 400])

        content.addWidget(center)
        content.setSizes([320, 1080])
        return content

    async def start(self, connection: StationFeedConnection) -> None:
        """Hydrate the window from the atomic StationFeed view and follow later complete views."""
        initial = connection.initial
        session = self._active_session(initial)
        self._devices.start(self._instrument, session)
        cfg = self._instrument.hardware_config.stage
        x, y, z = self._devices.get_adapter(cfg.x), self._devices.get_adapter(cfg.y), self._devices.get_adapter(cfg.z)
        if x and y and z:
            self._stage.bind(x, y, z)
        self._unsubs.append(self._preview.start_feed(self._instrument, self._station.feed, initial))
        self._feed_task = asyncio.create_task(self._follow_feed(connection), name="qt-station-feed")

    def _active_session(self, view: StationFeedView) -> SessionState:
        session = view.session
        if session is None or session.info.id != self._session.id:
            raise RuntimeError(f"station feed does not contain session '{self._session.id}'")
        return session

    async def _follow_feed(self, connection: StationFeedConnection) -> None:
        async for view in connection:
            if view.session is None or view.session.info.id != self._session.id:
                continue
            self._devices.apply_session(view.session)
            self._preview.apply_view(view)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Let the window close now; tear down stores and hand control back to the launcher async.
        self._ensure_shutdown()
        event.accept()

    def _ensure_shutdown(self) -> asyncio.Task[None]:
        if self._shutdown_task is None:
            self._shutdown_task = fire_and_forget(self._shutdown(), name="qt-control-shutdown", log=log)
        return self._shutdown_task

    async def shutdown(self) -> None:
        """Tear down the control window once and wait until its session can be released."""
        try:
            await self._ensure_shutdown()
        except Exception:
            log.exception("Control-window teardown failed")

    async def _shutdown(self) -> None:
        try:
            if self._feed_task is not None:
                self._feed_task.cancel()
                try:
                    await self._feed_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    log.exception("StationFeed follower failed")
                self._feed_task = None
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
            if self._logs is not None:
                self._logs.teardown()
                self._logs = None
            self._devices.stop()
            self._preview.reset()
            self._stage.unbind()
        finally:
            self._on_closed()


class LaunchWindow(QWidget):
    """The home window: lists instruments and launches one (spawning the control window and hiding
    itself; reappears when that window closes), and scaffolds new instruments from the shipped
    templates. Owns the Station and instrument-session lifecycle."""

    def __init__(
        self,
        station: Station,
        templates: InstrumentTemplates,
        request_quit: Callable[[], None],
    ) -> None:
        super().__init__()
        self._station = station
        self._templates_source = templates
        self._request_quit = request_quit
        self._control: MainWindow | None = None
        self._session_task: asyncio.Task[None] | None = None
        self._control_closed: asyncio.Event | None = None

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
        instruments = self._station.discover_instruments()
        templates = self._templates_source.discover()
        self._list.clear()
        if not instruments:
            self._list.add(Text.muted("No instruments yet — launch one from a template below."))
        else:
            for name, info in instruments.items():
                self._list.add(self._row(name, info))

        self._templates.clear()
        if not templates:
            self._templates.add(Text.muted("No templates available."))
        else:
            for name in templates:
                self._templates.add(self._template_row(name))

    def _row(self, name: str, info: InstrumentInspection) -> QWidget:
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
        self._start_session(name)

    def _launch_template(self, template: str) -> None:
        """Create an instrument from the template (named after it), then open it."""
        self._start_session(template, template=template)

    def _start_session(self, name: str, *, template: str | None = None) -> None:
        if self._session_task is not None and not self._session_task.done():
            return
        self._session_task = fire_and_forget(
            self._run_session(name, template=template),
            name="qt-instrument-session",
            log=log,
        )

    async def _run_session(self, name: str, *, template: str | None = None) -> None:
        """Own one complete Station session and lease for the control window lifetime."""
        label = template or name
        self._set_launching(True, label)
        session: SessionInfo | None = None
        try:
            if template is not None:
                await self._station.create_instrument(name, self._templates_source.get(template))
            session = await self._station.open_session(name)
            async with (
                self._station.instrument(session.id) as instrument,
                self._station.feed.connect() as connection,
            ):
                self._control_closed = asyncio.Event()
                self._control = MainWindow(
                    instrument,
                    self._station,
                    session,
                    on_closed=self._control_closed.set,
                )
                await self._control.start(connection)
                self._control.showMaximized()
                self.hide()
                await self._control_closed.wait()
        except FileExistsError:
            self._status.setText(f"An instrument named '{label}' already exists.")
            self._refresh()
        except Exception:
            log.exception("Failed to launch '%s'", label)
            self._status.setText(f"Failed to launch '{label}'.")
        finally:
            if self._control is not None:
                await self._control.shutdown()
            self._control = None
            self._control_closed = None
            if session is not None:
                try:
                    await self._station.close_session(session.id)
                except Exception:
                    log.exception("Failed to close instrument session '%s'", session.id)
            self._refresh()
            self.show()
            self._set_launching(False)

    def _set_launching(self, launching: bool, name: str = "") -> None:
        self._status.setText(f"Launching {name}…" if launching else "")
        self.setEnabled(not launching)

    async def shutdown(self) -> None:
        """Release any control-window lease and close the Station before process exit."""
        if self._control is not None:
            await self._control.shutdown()
        if self._session_task is not None and self._session_task is not asyncio.current_task():
            with suppress(asyncio.CancelledError):
                await self._session_task
        await self._station.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        # The root coroutine closes Station before allowing qasync to stop Qt.
        self.setEnabled(False)
        self.hide()
        self._request_quit()
        event.ignore()


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


async def _run_station_app(station: Station, templates: InstrumentTemplates) -> None:
    """Run the Qt composition under durable log capture and close Station on exit."""
    async with station.records.logs.capture():
        stopped = asyncio.Event()
        window = LaunchWindow(station, templates, stopped.set)
        window.show()
        log.info("Voxel application started")
        try:
            await stopped.wait()
        finally:
            await window.shutdown()
            log.info("Voxel application stopped")


def run_app(_config_path: Path | None = None, *, log_level: int = logging.INFO) -> int:
    """Run the Voxel application with the qasync event loop. Returns the process exit code."""
    configure_logging(log_level)
    qapp = create_qapp()
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    try:
        with loop:
            loop.run_until_complete(
                _run_station_app(
                    Station(StationConfig.load()),
                    InstrumentTemplates(),
                )
            )
    except KeyboardInterrupt:
        log.info("Application interrupted")
    except Exception:
        log.exception("Application error")
        return 1
    return 0


def launch(config: Path | None = None, *, verbose: bool = False) -> int:
    """Run the Qt application after loading Voxel's ambient environment."""
    load_voxel_env()  # ambient env from ~/.voxel/.env before anything reads it (System, S3 clients)
    return run_app(config, log_level=logging.DEBUG if verbose else logging.INFO)

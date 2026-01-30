"""Main application window with view switching.

Manages the top-level window and switches between views based on app phase:
- idle: LaunchPage (session selection)
- launching: LaunchPage with loading indicator
- ready: ControlPage (main operational interface)

The MainWindow orchestrates the connection between LaunchPage (pure view)
and VoxelApp (application logic).
"""

import logging

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
)

from vxl.system import SessionDirectory
from vxl_qt.app import VoxelApp
from vxl_qt.ui.control_page import ControlPage
from vxl_qt.ui.kit import Colors
from vxl_qt.ui.launch_page import LaunchPage
from vxlib import fire_and_forget

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with phase-based view switching.

    The window uses a QStackedWidget to switch between:
    - LaunchPage (phase='idle')
    - ControlPage (phase='ready')

    Usage:
        app = VoxelApp()
        window = MainWindow(app)
        window.show()
    """

    def __init__(self, app: VoxelApp) -> None:
        super().__init__()
        self._app = app

        # Create widgets
        self._stack = QStackedWidget()
        self._launch_page = LaunchPage()
        self._control_page = ControlPage(self._app)

        self._configure_window()
        self._configure_layout()
        self._connect_signals()
        self._refresh_launch_page()

        # Set initial view based on current phase
        self._on_phase_changed(app.phase)

    def _configure_window(self) -> None:
        """Configure window properties."""
        self.setWindowTitle("Voxel Qt")
        self.setMinimumSize(1280, 800)
        self.showMaximized()
        # self.showFullScreen()

        # Apply dark theme
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Colors.BG_DARK};
            }}
            QWidget {{
                color: {Colors.TEXT};
            }}
        """)

    def _configure_layout(self) -> None:
        """Arrange widgets into layouts."""
        self.setCentralWidget(self._stack)
        self._stack.addWidget(self._launch_page)
        self._stack.addWidget(self._control_page)

    def _connect_signals(self) -> None:
        """Connect app signals to UI updates."""
        # App state signals
        self._app.phase_changed.connect(self._on_phase_changed)
        self._app.error_changed.connect(self._on_error)

        # LaunchPage user intent signals
        self._launch_page.new_session_requested.connect(self._on_new_session_requested)
        self._launch_page.session_resumed.connect(self._on_session_resumed)

    def _refresh_launch_page(self) -> None:
        """Refresh launch page data from app."""
        self._launch_page.set_roots(self._app.session_roots)
        self._launch_page.set_rigs(self._app.available_rigs)
        self._launch_page.set_sessions(self._app.list_all_sessions())

    @Slot(str)
    def _on_phase_changed(self, phase: str) -> None:
        """Handle app phase changes by switching views."""
        log.debug("Phase changed to: %s", phase)

        if phase == "idle":
            self._launch_page.set_launching(False)
            self._refresh_launch_page()
            self._stack.setCurrentWidget(self._launch_page)
        elif phase == "launching":
            # Keep launch page visible during launching so logs are visible
            self._launch_page.set_launching(True)
            self._stack.setCurrentWidget(self._launch_page)
        elif phase == "ready":
            self._control_page.refresh()
            self._stack.setCurrentWidget(self._control_page)

    @Slot(str, str, str)
    def _on_new_session_requested(self, root_name: str, session_name: str, rig_config: str) -> None:
        """Handle new session creation request from LaunchPage."""
        log.info("Creating new session: %s/%s with rig %s", root_name, session_name, rig_config)
        fire_and_forget(self._launch_session(root_name, session_name, rig_config), log=log)

    @Slot(object)
    def _on_session_resumed(self, session: SessionDirectory) -> None:
        """Handle session resume request from LaunchPage."""
        log.info("Resuming session: %s/%s", session.root_name, session.name)
        fire_and_forget(self._launch_session(session.root_name, session.name), log=log)

    async def _launch_session(self, root_name: str, session_name: str, rig_config: str | None = None) -> None:
        """Launch a session (new or resumed)."""
        try:
            await self._app.launch_session(root_name, session_name, rig_config)
        except Exception:
            log.exception("Failed to launch session")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        """Handle application errors."""
        log.error("Application error: %s", message)
        # TODO: Show error dialog or status bar message

    def closeEvent(self, event) -> None:
        """Handle window close - prompt for confirmation and cleanup."""
        if self._app.session is not None:
            # Ask for confirmation
            reply = QMessageBox.question(
                self,
                "Quit Voxel Qt",
                "An active session is running.\n\nAre you sure you want to quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            # Close session and quit
            log.info("User confirmed quit - closing session")
            fire_and_forget(self._close_and_quit(), log=log)
            event.ignore()  # We'll quit after cleanup
        else:
            # No session - just quit
            self._quit_app()
            event.accept()

    async def _close_and_quit(self) -> None:
        """Close the session and quit the application."""
        try:
            await self._app.close_session()
        except Exception:
            log.exception("Error closing session")
        finally:
            self._quit_app()

    def _quit_app(self) -> None:
        """Quit the Qt application."""
        log.info("Quitting application")
        app = QApplication.instance()
        if app:
            app.quit()

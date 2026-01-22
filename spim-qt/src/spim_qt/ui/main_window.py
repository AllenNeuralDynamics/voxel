"""Main application window with view switching.

Manages the top-level window and switches between views based on app phase:
- idle: LaunchPage (session selection)
- launching: LoadingView (spinner)
- ready: ControlPage (main operational interface)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spim_qt.ui.primitives.display import Label
from spim_qt.ui.theme import Colors

if TYPE_CHECKING:
    from spim_qt.app import SpimQtApp

log = logging.getLogger(__name__)


class LoadingView(QWidget):
    """Simple loading view shown during session launch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Centered loading message
        self._label = Label("Starting Session...", variant="title")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self._label)
        layout.addStretch()

    def set_message(self, message: str) -> None:
        """Update the loading message."""
        self._label.setText(message)


class MainWindow(QMainWindow):
    """Main application window with phase-based view switching.

    The window uses a QStackedWidget to switch between:
    - LaunchPage (phase='idle')
    - LoadingView (phase='launching')
    - ControlPage (phase='ready')

    Usage:
        app = SpimQtApp()
        window = MainWindow(app)
        window.show()
    """

    def __init__(self, app: SpimQtApp) -> None:
        super().__init__()
        self._app = app

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        # Set initial view based on current phase
        self._on_phase_changed(app.phase)

    def _setup_window(self) -> None:
        """Configure window properties."""
        self.setWindowTitle("SPIM Qt")
        self.setMinimumSize(1280, 800)
        self.resize(1600, 1000)

        # Apply dark theme
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Colors.BG_DARK};
            }}
            QWidget {{
                color: {Colors.TEXT};
            }}
        """)

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        # Central stacked widget for view switching
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Loading view (always available)
        self._loading_view = LoadingView()
        self._stack.addWidget(self._loading_view)

        # Launch page (lazy import to avoid circular imports)
        from spim_qt.ui.launch import LaunchPage

        self._launch_page = LaunchPage(self._app)
        self._stack.addWidget(self._launch_page)

        # Control page (lazy import)
        from spim_qt.ui.control import ControlPage

        self._control_page = ControlPage(self._app)
        self._stack.addWidget(self._control_page)

    def _connect_signals(self) -> None:
        """Connect app signals to UI updates."""
        self._app.phase_changed.connect(self._on_phase_changed)
        self._app.error_occurred.connect(self._on_error)

    @Slot(str)
    def _on_phase_changed(self, phase: str) -> None:
        """Handle app phase changes by switching views."""
        log.debug("Phase changed to: %s", phase)

        if phase == "idle":
            self._stack.setCurrentWidget(self._launch_page)
        elif phase == "launching":
            self._loading_view.set_message("Starting Session...\nInitializing rig and devices...")
            self._stack.setCurrentWidget(self._loading_view)
        elif phase == "ready":
            self._control_page.refresh()
            self._stack.setCurrentWidget(self._control_page)

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
                "Quit SPIM Qt",
                "An active session is running.\n\nAre you sure you want to quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

            # Close session and quit
            log.info("User confirmed quit - closing session")
            asyncio.create_task(self._close_and_quit())
            event.ignore()  # We'll quit after cleanup
        else:
            # No session - just quit
            self._quit_app()
            event.accept()

    async def _close_and_quit(self) -> None:
        """Close the session and quit the application."""
        try:
            await self._app.close_session()
        except Exception as e:
            log.error("Error closing session: %s", e)
        finally:
            self._quit_app()

    def _quit_app(self) -> None:
        """Quit the Qt application."""
        log.info("Quitting application")
        app = QApplication.instance()
        if app:
            app.quit()

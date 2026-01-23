"""Voxel Qt application entry point with qasync event loop integration."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from voxel_qt.app import VoxelQtApp
from voxel_qt.ui.main_window import MainWindow
from voxel_qt.ui.theme import Colors


def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging with a simple format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def create_qapp() -> QApplication:
    """Create and configure the Qt application."""
    qapp = QApplication([])
    qapp.setStyle("Fusion")
    qapp.setApplicationName("Voxel Qt")

    # Apply dark palette using design tokens
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
    qapp.setPalette(palette)

    return qapp


def run_app(_config_path: Path | None = None) -> int:
    """Run the Voxel Qt application with qasync event loop.

    Args:
        config_path: Optional path to rig configuration YAML

    Returns:
        Exit code (0 for success)
    """
    configure_logging(logging.INFO)
    log = logging.getLogger(__name__)

    qapp = create_qapp()
    loop = qasync.QEventLoop(qapp)
    asyncio.set_event_loop(loop)

    # Keep references to prevent garbage collection
    window = None

    async def _setup_and_run() -> None:
        """Setup and show the main window."""
        nonlocal window

        # Create application state manager
        app = VoxelQtApp()

        # Create and show main window
        window = MainWindow(app)
        window.show()

        log.info("Voxel Qt application started")

    try:
        with loop:
            loop.run_until_complete(_setup_and_run())
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
        description="Voxel Qt - Microscope control application",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        help="Path to rig configuration YAML file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        configure_logging(logging.DEBUG)

    sys.exit(run_app(args.config))


if __name__ == "__main__":
    main()

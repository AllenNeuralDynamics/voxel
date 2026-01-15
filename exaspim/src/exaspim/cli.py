"""ExASPIM application entry point with qasync event loop integration."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from exaspim.ui.theme import Colors


def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging with a simple format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def create_app() -> QApplication:
    """Create and configure the Qt application."""
    app = QApplication([])
    app.setStyle("Fusion")
    app.setApplicationName("ExASPIM")

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
    app.setPalette(palette)

    return app


def run_app(config_path: Path | None = None) -> int:
    """Run the ExASPIM application with qasync event loop.

    Args:
        config_path: Optional path to rig configuration YAML

    Returns:
        Exit code (0 for success)
    """
    configure_logging(logging.INFO)
    log = logging.getLogger(__name__)

    app = create_app()
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    async def _setup_and_run() -> None:
        """Setup and show the main window."""
        # TODO: Import and create MainWindow
        # from exaspim.ui.main import MainWindow
        # window = MainWindow(config_path)
        # window.show()
        log.info("ExASPIM application started")
        log.info("Main window not yet implemented - placeholder")

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
        description="ExASPIM microscope control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        help="Path to rig configuration YAML file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        configure_logging(logging.DEBUG)

    sys.exit(run_app(args.config))


if __name__ == "__main__":
    main()

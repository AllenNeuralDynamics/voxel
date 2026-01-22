"""SPIM Qt - PySide6-based microscope control built on spim-rig.

This package provides a native Qt desktop application for SPIM microscope control,
offering the same features as the spim-studio web interface but as a desktop app.

Key components:
- SpimQtApp: Application state manager
- MainWindow: Main application window
- Launch/Control pages: Session management and operational UI
"""

__version__ = "0.1.0"

from spim_qt.app import SpimQtApp

__all__ = ["SpimQtApp", "__version__"]

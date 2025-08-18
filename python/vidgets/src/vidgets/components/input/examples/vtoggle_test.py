#!/usr/bin/env python3
"""
Quick VToggle Test

A minimal test to verify VToggle animation functionality.
"""

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from vidgets.components.input.toggle import VToggle


def main():
    """Quick test of VToggle animation."""
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("VToggle Quick Test")
    window.setGeometry(300, 300, 300, 200)

    layout = QVBoxLayout(window)

    label = QLabel("VToggle Animation Test")
    layout.addWidget(label)

    # Create a VToggle
    toggle = VToggle()
    layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignCenter)

    # Status label
    status = QLabel("Toggle: OFF")
    layout.addWidget(status)

    # Update status when toggled
    def update_status(checked):
        status.setText(f"Toggle: {'ON' if checked else 'OFF'}")
        print(f"VToggle state changed: {'ON' if checked else 'OFF'}")

    toggle.toggled.connect(update_status)

    # Auto-toggle for demo (optional)
    timer = QTimer()
    timer.timeout.connect(lambda: toggle.setChecked(not toggle.isChecked()))
    # timer.start(2000)  # Auto-toggle every 2 seconds (commented out)

    window.show()

    print("VToggle test window opened. Click the toggle to test animation!")
    print("The toggle should smoothly animate between states with a pulse effect.")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

"""Test script to verify empty slot rendering in filter wheel widget."""

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from spim_widgets.filter_wheel.graphic import WheelGraphic


class TestWindow(QMainWindow):
    """Test window for filter wheel graphic."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Empty Slot Rendering Test")
        self.setGeometry(100, 100, 600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Add instruction label
        label = QLabel(
            "Testing empty slot rendering:\n"
            "- Slots 3 and 5 should appear with dim gray strokes (empty)\n"
            "- Other slots should have colored strokes\n"
            "- NO RED should appear on empty slots"
        )
        layout.addWidget(label)

        # Create wheel graphic with some empty slots (None) and some filled slots
        self.graphic = WheelGraphic(
            num_slots=6,
            assignments={
                0: "655LP",  # Should be red
                1: "620/60BP",  # Should be green
                2: "500LP",  # Should be blue
                3: None,  # Should be empty (dim gray)
                4: "DAPI",  # Should use default hue (blue-gray, not red!)
                5: None,  # Should be empty (dim gray)
            },
            hue_mapping={
                "655LP": 0,  # red
                "620/60BP": 120,  # green
                "500LP": 230,  # blue
                # Note: "DAPI" not in mapping, will use default_hue = 240 (blue-gray)
            },
        )
        layout.addWidget(self.graphic)


def main():
    """Run the test application."""
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from spim_widgets.ui.input.toggle import VToggle


class VToggleDemo(QMainWindow):
    """Demo window showing various VToggle configurations."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VToggle Component Demo")
        self.setGeometry(100, 100, 500, 600)
        self.setup_ui()

    def setup_ui(self):
        """Set up the demo interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("VToggle Component Demo")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Functional Toggles (with callbacks)
        functional_group = self.create_functional_toggles()
        layout.addWidget(functional_group)

        # State Display
        self.state_label = QLabel("Toggle States: All unchecked")
        self.state_label.setProperty("class", "state-label")
        layout.addWidget(self.state_label)

        # Control Buttons
        button_layout = QHBoxLayout()

        check_all_btn = QPushButton("Check All")
        check_all_btn.clicked.connect(self.check_all_toggles)
        button_layout.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("Uncheck All")
        uncheck_all_btn.clicked.connect(self.uncheck_all_toggles)
        button_layout.addWidget(uncheck_all_btn)

        layout.addLayout(button_layout)

        layout.addStretch()

    def create_functional_toggles(self) -> QGroupBox:
        """Create toggles with functional behavior using VToggleSwitch."""
        group = QGroupBox("Functional VToggleSwitch Examples")
        layout = QVBoxLayout(group)

        # Dark mode toggle
        dark_layout = QHBoxLayout()
        dark_layout.addWidget(QLabel("Dark Mode:"))
        self.dark_toggle = VToggle(text="Dark Mode", setter=self.on_dark_mode_changed, checked_color="#4CAF50")
        dark_layout.addWidget(self.dark_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        dark_layout.addStretch()
        layout.addLayout(dark_layout)

        # Notifications toggle
        notif_layout = QHBoxLayout()
        notif_layout.addWidget(QLabel("Notifications:"))
        self.notif_toggle = VToggle(text="Notifications", setter=self.on_notifications_changed, checked_color="#FF9800")
        notif_layout.addWidget(self.notif_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        notif_layout.addStretch()
        layout.addLayout(notif_layout)

        return group

    def on_dark_mode_changed(self, checked: bool):
        """Handle dark mode toggle."""
        print(f"Dark mode {'enabled' if checked else 'disabled'}")
        self.update_state_display()

    def on_notifications_changed(self, checked: bool):
        """Handle notifications toggle."""
        print(f"Notifications {'enabled' if checked else 'disabled'}")
        self.update_state_display()

    def update_state_display(self):
        """Update the state display label."""
        states = []

        if hasattr(self, "dark_toggle") and self.dark_toggle.isChecked():
            states.append("Dark Mode")
        if hasattr(self, "notif_toggle") and self.notif_toggle.isChecked():
            states.append("Notifications")

        if states:
            self.state_label.setText(f"Active Toggles: {', '.join(states)}")
        else:
            self.state_label.setText("Toggle States: All unchecked")

    def check_all_toggles(self):
        """Check all toggles."""
        if hasattr(self, "dark_toggle"):
            self.dark_toggle.setChecked(True)
        if hasattr(self, "notif_toggle"):
            self.notif_toggle.setChecked(True)

    def uncheck_all_toggles(self):
        """Uncheck all toggles."""
        if hasattr(self, "dark_toggle"):
            self.dark_toggle.setChecked(False)
        if hasattr(self, "notif_toggle"):
            self.notif_toggle.setChecked(False)


def main():
    """Run the VToggle demo application."""
    app = QApplication(sys.argv)
    app.setApplicationName("VToggle Demo")

    # Set a modern style
    app.setStyle("Fusion")

    demo = VToggleDemo()
    demo.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

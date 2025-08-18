import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QGroupBox,
    QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from vidgets.components.input.toggle import VToggle


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

        # Basic Toggle Group
        basic_group = self.create_basic_toggles()
        layout.addWidget(basic_group)

        # Custom Color Toggles
        color_group = self.create_color_toggles()
        layout.addWidget(color_group)

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

    def create_basic_toggles(self) -> QGroupBox:
        """Create basic toggle examples."""
        group = QGroupBox("Basic VToggle Examples")
        layout = QVBoxLayout(group)

        # Simple toggle
        toggle_layout = QHBoxLayout()
        toggle_layout.addWidget(QLabel("Simple Toggle:"))
        self.basic_toggle = VToggle()
        self.basic_toggle.toggled.connect(self.update_state_display)
        toggle_layout.addWidget(self.basic_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        # Pre-checked toggle
        checked_layout = QHBoxLayout()
        checked_layout.addWidget(QLabel("Pre-checked Toggle:"))
        self.checked_toggle = VToggle()
        self.checked_toggle.setChecked(True)
        self.checked_toggle.toggled.connect(self.update_state_display)
        checked_layout.addWidget(self.checked_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        checked_layout.addStretch()
        layout.addLayout(checked_layout)

        return group

    def create_color_toggles(self) -> QGroupBox:
        """Create toggles with custom colors."""
        group = QGroupBox("Custom Color VToggle Examples")
        layout = QVBoxLayout(group)

        # Blue toggle
        blue_layout = QHBoxLayout()
        blue_layout.addWidget(QLabel("Blue Theme:"))
        self.blue_toggle = VToggle(checked_color="#2196F3", pulse_checked_color="#442196F3")
        self.blue_toggle.toggled.connect(self.update_state_display)
        blue_layout.addWidget(self.blue_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        blue_layout.addStretch()
        layout.addLayout(blue_layout)

        # Green toggle
        green_layout = QHBoxLayout()
        green_layout.addWidget(QLabel("Green Theme:"))
        self.green_toggle = VToggle(checked_color="#4CAF50", pulse_checked_color="#444CAF50")
        self.green_toggle.toggled.connect(self.update_state_display)
        green_layout.addWidget(self.green_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        green_layout.addStretch()
        layout.addLayout(green_layout)

        # Orange toggle
        orange_layout = QHBoxLayout()
        orange_layout.addWidget(QLabel("Orange Theme:"))
        self.orange_toggle = VToggle(checked_color="#FF9800", pulse_checked_color="#44FF9800")
        self.orange_toggle.toggled.connect(self.update_state_display)
        orange_layout.addWidget(self.orange_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        orange_layout.addStretch()
        layout.addLayout(orange_layout)

        return group

    def create_functional_toggles(self) -> QGroupBox:
        """Create toggles with functional behavior using VToggleSwitch."""
        group = QGroupBox("Functional VToggleSwitch Examples")
        layout = QVBoxLayout(group)

        # Dark mode toggle
        dark_layout = QHBoxLayout()
        dark_layout.addWidget(QLabel("Dark Mode:"))
        self.dark_toggle = VToggle(text="Dark Mode", setter=self.on_dark_mode_changed)
        dark_layout.addWidget(self.dark_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        dark_layout.addStretch()
        layout.addLayout(dark_layout)

        # Notifications toggle
        notif_layout = QHBoxLayout()
        notif_layout.addWidget(QLabel("Notifications:"))
        self.notif_toggle = VToggle(text="Notifications", setter=self.on_notifications_changed)
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

        if hasattr(self, "basic_toggle") and self.basic_toggle.isChecked():
            states.append("Basic")
        if hasattr(self, "checked_toggle") and self.checked_toggle.isChecked():
            states.append("Pre-checked")
        if hasattr(self, "blue_toggle") and self.blue_toggle.isChecked():
            states.append("Blue")
        if hasattr(self, "green_toggle") and self.green_toggle.isChecked():
            states.append("Green")
        if hasattr(self, "orange_toggle") and self.orange_toggle.isChecked():
            states.append("Orange")
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
        if hasattr(self, "basic_toggle"):
            self.basic_toggle.setChecked(True)
        if hasattr(self, "checked_toggle"):
            self.checked_toggle.setChecked(True)
        if hasattr(self, "blue_toggle"):
            self.blue_toggle.setChecked(True)
        if hasattr(self, "green_toggle"):
            self.green_toggle.setChecked(True)
        if hasattr(self, "orange_toggle"):
            self.orange_toggle.setChecked(True)
        if hasattr(self, "dark_toggle"):
            self.dark_toggle.setChecked(True)
        if hasattr(self, "notif_toggle"):
            self.notif_toggle.setChecked(True)

    def uncheck_all_toggles(self):
        """Uncheck all toggles."""
        if hasattr(self, "basic_toggle"):
            self.basic_toggle.setChecked(False)
        if hasattr(self, "checked_toggle"):
            self.checked_toggle.setChecked(False)
        if hasattr(self, "blue_toggle"):
            self.blue_toggle.setChecked(False)
        if hasattr(self, "green_toggle"):
            self.green_toggle.setChecked(False)
        if hasattr(self, "orange_toggle"):
            self.orange_toggle.setChecked(False)
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

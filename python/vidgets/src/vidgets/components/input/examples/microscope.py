"""
Microscope Control Interface Example

This example demonstrates a realistic microscope control interface built using
the Voxel input components. It showcases how to create a proper UI application
with state management, status indicators, and organized control panels.
"""

import json
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from vidgets.components.extras.drawer import SlidingDrawer
from vidgets.components.input.input_group import FlowDirection, create_input_group
from vidgets.components.input.label import VLabel
from vidgets.components.input.number import VNumberInput
from vidgets.components.input.select import VSelect
from vidgets.components.input.text import VTextInput
from vidgets.components.input.toggle import VToggle


class MicroscopeState:
    """Simulated microscope state that components will read from."""

    def __init__(self):
        # Camera settings
        self.camera_enabled = True
        self.exposure_time = 0.1
        self.gain = 100
        self.binning = "1x1"

        # Laser settings
        self.laser_405_enabled = False
        self.laser_488_enabled = True
        self.laser_561_enabled = False
        self.laser_405_power = 5.0
        self.laser_488_power = 15.0
        self.laser_561_power = 10.0

        # Stage settings
        self.stage_x = 1000.0
        self.stage_y = 500.0
        self.stage_z = 250.0
        self.stage_step_size = 10.0

        # Experiment settings
        self.experiment_name = "ExaSPIM_Acquisition"
        self.sample_id = "Sample_001"
        self.objective_lens = "20x/0.8 NA"
        self.acquisition_mode = "Time Series"

        # System status
        self.temperature = 23.5
        self.humidity = 45.0
        self.system_ready = True

    def update_value(self, path: str, value):
        """Update a value in the state using dot notation."""
        setattr(self, path, value)

    def to_dict(self) -> dict:
        """Convert state to dictionary for logging."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class MicroscopeControlInterface(QMainWindow):
    """Main microscope control interface."""

    def __init__(self):
        super().__init__()
        self.state = MicroscopeState()
        # UI components that will be initialized in setup_ui
        self.config_display = None
        self.temp_label = None
        self.humidity_label = None
        self.ready_label = None
        self.drawer = None

        self.setup_ui()
        self.setup_status_updates()

    def setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("ExaSPIM Microscope Control - Voxel Components Demo")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget with main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout for the entire window
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # Create top header with toggle button
        header_layout = QHBoxLayout()
        header_layout.addStretch()  # Push button to the right

        # Toggle checkbox styled as button in top right corner
        self.log_toggle_button = QCheckBox("📋")
        self.log_toggle_button.setFixedSize(40, 30)
        self.log_toggle_button.setStyleSheet("""
            QCheckBox {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 16px;
            }
            QCheckBox:hover {
                background-color: #45a049;
            }
            QCheckBox:checked {
                background-color: #2196F3;
            }
            QCheckBox:checked:hover {
                background-color: #1976D2;
            }
            QCheckBox::indicator {
                width: 0px;
                height: 0px;
            }
        """)
        self.log_toggle_button.setToolTip("Toggle Event Log (Ctrl+L)")
        self.log_toggle_button.toggled.connect(self.toggle_log_drawer)

        header_layout.addWidget(self.log_toggle_button)
        main_layout.addLayout(header_layout)

        # Create controls and status panels
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        content_layout.addWidget(splitter)

        # Left panel - Controls
        controls_widget = self.create_controls_panel()
        splitter.addWidget(controls_widget)

        # Right panel - Status (without log now)
        status_widget = self.create_status_panel()
        splitter.addWidget(status_widget)

        # Set splitter proportions
        splitter.setSizes([800, 400])

        main_layout.addWidget(content_widget)

        # Create the sliding drawer (50% of window width)
        drawer_width = int(self.width() * 0.5)
        self.drawer = SlidingDrawer(central_widget, width=drawer_width)

        # Status bar (no toggle button now)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("System Ready | Press Ctrl+L to toggle Event Log")

        # Add keyboard shortcut for toggling log (Ctrl+L)
        self.log_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self.log_shortcut.activated.connect(self.keyboard_toggle_log)

    def create_controls_panel(self) -> QWidget:
        """Create the left panel with all control groups."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Title
        title = VLabel("Microscope Controls")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Experiment Info Group
        exp_group = self.create_experiment_group()
        layout.addWidget(exp_group)

        # Camera Controls Group
        camera_group = self.create_camera_group()
        layout.addWidget(camera_group)

        # Laser Controls Group
        laser_group = self.create_laser_group()
        layout.addWidget(laser_group)

        # Stage Controls Group
        stage_group = self.create_stage_group()
        layout.addWidget(stage_group)

        # Toggle Demos Group
        toggle_group = self.create_toggle_demos_group()
        layout.addWidget(toggle_group)

        # Action Buttons
        buttons_group = self.create_action_buttons()
        layout.addWidget(buttons_group)

        layout.addStretch()
        return widget

    def create_experiment_group(self) -> QGroupBox:
        """Create experiment information controls."""
        group = QGroupBox("Experiment Setup")
        layout = QVBoxLayout(group)

        controls = create_input_group(
            {
                "Experiment Name": VTextInput(
                    getter=lambda: self.state.experiment_name, setter=self.make_callback("experiment_name")
                ),
                "Sample ID": VTextInput(getter=lambda: self.state.sample_id, setter=self.make_callback("sample_id")),
                "Objective": VSelect(
                    ["10x/0.3 NA", "20x/0.8 NA", "40x/0.9 NA", "63x/1.4 NA"],
                    getter=lambda: self.state.objective_lens,
                    setter=self.make_callback("objective_lens"),
                ),
                "Acquisition Mode": VSelect(
                    ["Single Image", "Time Series", "Z-Stack", "Tile Scan"],
                    getter=lambda: self.state.acquisition_mode,
                    setter=self.make_callback("acquisition_mode"),
                ),
            },
            flow=FlowDirection.FORM,
        )

        layout.addWidget(controls)
        return group

    def create_camera_group(self) -> QGroupBox:
        """Create camera control panel."""
        group = QGroupBox("Camera Settings")
        layout = QVBoxLayout(group)

        controls = create_input_group(
            {
                "Camera Enable": VToggle(
                    getter=lambda: self.state.camera_enabled, setter=self.make_callback("camera_enabled")
                ),
                "Exposure (s)": VNumberInput(
                    min_value=0.001,
                    max_value=10.0,
                    decimals=3,
                    getter=lambda: self.state.exposure_time,
                    setter=self.make_callback("exposure_time"),
                    parent=self,
                ),
                "Gain": VNumberInput(
                    min_value=1,
                    max_value=1000,
                    getter=lambda: self.state.gain,
                    setter=self.make_callback("gain"),
                    parent=self,
                ),
                "Binning": VSelect(
                    ["1x1", "2x2", "4x4"], getter=lambda: self.state.binning, setter=self.make_callback("binning")
                ),
            },
            flow=FlowDirection.FORM,
        )

        layout.addWidget(controls)
        return group

    def create_laser_group(self) -> QGroupBox:
        """Create laser control panel."""
        group = QGroupBox("Laser Controls")
        layout = QVBoxLayout(group)

        # 405nm Laser
        laser_405 = create_input_group(
            {
                "405nm Enable": VToggle(
                    getter=lambda: self.state.laser_405_enabled, setter=self.make_callback("laser_405_enabled")
                ),
                "Power (mW)": VNumberInput(
                    min_value=0.0,
                    max_value=50.0,
                    decimals=1,
                    getter=lambda: self.state.laser_405_power,
                    setter=self.make_callback("laser_405_power"),
                    parent=self,
                ),
            },
            flow=FlowDirection.HORIZONTAL,
        )

        # 488nm Laser
        laser_488 = create_input_group(
            {
                "488nm Enable": VToggle(
                    getter=lambda: self.state.laser_488_enabled, setter=self.make_callback("laser_488_enabled")
                ),
                "Power (mW)": VNumberInput(
                    min_value=0.0,
                    max_value=100.0,
                    decimals=1,
                    getter=lambda: self.state.laser_488_power,
                    setter=self.make_callback("laser_488_power"),
                    parent=self,
                ),
            },
            flow=FlowDirection.HORIZONTAL,
        )

        # 561nm Laser
        laser_561 = create_input_group(
            {
                "561nm Enable": VToggle(
                    getter=lambda: self.state.laser_561_enabled, setter=self.make_callback("laser_561_enabled")
                ),
                "Power (mW)": VNumberInput(
                    min_value=0.0,
                    max_value=75.0,
                    decimals=1,
                    getter=lambda: self.state.laser_561_power,
                    setter=self.make_callback("laser_561_power"),
                    parent=self,
                ),
            },
            flow=FlowDirection.HORIZONTAL,
        )

        layout.addWidget(laser_405)
        layout.addWidget(laser_488)
        layout.addWidget(laser_561)
        return group

    def create_stage_group(self) -> QGroupBox:
        """Create stage control panel."""
        group = QGroupBox("Stage Position")
        layout = QVBoxLayout(group)

        position_controls = create_input_group(
            {
                "X (μm)": VNumberInput(
                    min_value=0.0,
                    max_value=25000.0,
                    decimals=1,
                    getter=lambda: self.state.stage_x,
                    setter=self.make_callback("stage_x"),
                    parent=self,
                ),
                "Y (μm)": VNumberInput(
                    min_value=0.0,
                    max_value=25000.0,
                    decimals=1,
                    getter=lambda: self.state.stage_y,
                    setter=self.make_callback("stage_y"),
                    parent=self,
                ),
                "Z (μm)": VNumberInput(
                    min_value=0.0,
                    max_value=1000.0,
                    decimals=1,
                    getter=lambda: self.state.stage_z,
                    setter=self.make_callback("stage_z"),
                    parent=self,
                ),
                "Step Size (μm)": VNumberInput(
                    min_value=0.1,
                    max_value=1000.0,
                    decimals=1,
                    getter=lambda: self.state.stage_step_size,
                    setter=self.make_callback("stage_step_size"),
                    parent=self,
                ),
            },
            flow=FlowDirection.GRID,
        )

        layout.addWidget(position_controls)
        return group

    def create_toggle_demos_group(self) -> QGroupBox:
        """Create toggle demonstrations group."""
        group = QGroupBox("Animated Toggles Demo")
        layout = QVBoxLayout(group)

        # Basic VToggle examples
        toggles_layout = QHBoxLayout()

        # Standard toggle with default blue theme
        standard_toggle = VToggle()
        standard_toggle.setChecked(True)
        standard_label = VLabel("Standard Toggle")

        # Custom colored toggle (green theme)
        green_toggle = VToggle(checked_color="#4CAF50", pulse_checked_color="#444CAF50")
        green_label = VLabel("Green Toggle")

        # Custom colored toggle (orange theme)
        orange_toggle = VToggle(checked_color="#FF9800", pulse_checked_color="#44FF9800")
        orange_label = VLabel("Orange Toggle")

        # Add toggles with labels
        standard_container = QVBoxLayout()
        standard_container.addWidget(standard_label)
        standard_container.addWidget(standard_toggle, 0, Qt.AlignmentFlag.AlignCenter)

        green_container = QVBoxLayout()
        green_container.addWidget(green_label)
        green_container.addWidget(green_toggle, 0, Qt.AlignmentFlag.AlignCenter)

        orange_container = QVBoxLayout()
        orange_container.addWidget(orange_label)
        orange_container.addWidget(orange_toggle, 0, Qt.AlignmentFlag.AlignCenter)

        # Create containers
        standard_widget = QWidget()
        standard_widget.setLayout(standard_container)
        green_widget = QWidget()
        green_widget.setLayout(green_container)
        orange_widget = QWidget()
        orange_widget.setLayout(orange_container)

        toggles_layout.addWidget(standard_widget)
        toggles_layout.addWidget(green_widget)
        toggles_layout.addWidget(orange_widget)
        toggles_layout.addStretch()

        # VToggleSwitch examples with functional callbacks
        functional_layout = QVBoxLayout()
        functional_label = VLabel("Functional Toggles (with callbacks)")
        functional_layout.addWidget(functional_label)

        # Auto-focus toggle
        autofocus_toggle = VToggle(
            text="Auto Focus",
            getter=lambda: getattr(self.state, "autofocus_enabled", False),
            setter=lambda checked: self.log_message(f"Auto-focus {'enabled' if checked else 'disabled'}"),
            checked_color="#2196F3",
        )

        # Live preview toggle
        preview_toggle = VToggle(
            text="Live Preview",
            getter=lambda: getattr(self.state, "preview_enabled", True),
            setter=lambda checked: self.log_message(f"Live preview {'enabled' if checked else 'disabled'}"),
            checked_color="#9C27B0",
        )

        functional_layout.addWidget(autofocus_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        functional_layout.addWidget(preview_toggle, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(toggles_layout)
        layout.addLayout(functional_layout)
        return group

    def create_action_buttons(self) -> QGroupBox:
        """Create action buttons group."""
        group = QGroupBox("Actions")
        layout = QHBoxLayout(group)

        start_btn = QPushButton("Start Acquisition")
        start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }"
        )
        start_btn.clicked.connect(self.start_acquisition)

        stop_btn = QPushButton("Stop")
        stop_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px; }"
        )
        stop_btn.clicked.connect(self.stop_acquisition)

        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self.save_configuration)

        load_btn = QPushButton("Load Config")
        load_btn.clicked.connect(self.load_configuration)

        layout.addWidget(start_btn)
        layout.addWidget(stop_btn)
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)

        return group

    def create_status_panel(self) -> QWidget:
        """Create the right panel with status information (no log - now in drawer)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status indicators
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout(status_group)

        self.temp_label = VLabel(f"Temperature: {self.state.temperature:.1f} °C")
        self.humidity_label = VLabel(f"Humidity: {self.state.humidity:.1f} %")
        self.ready_label = VLabel("System Ready: ✓ Ready" if self.state.system_ready else "System Ready: ✗ Not Ready")

        status_layout.addWidget(self.temp_label)
        status_layout.addWidget(self.humidity_label)
        status_layout.addWidget(self.ready_label)
        layout.addWidget(status_group)

        # Current configuration display (takes more space now)
        config_group = QGroupBox("Current Configuration")
        config_layout = QVBoxLayout(config_group)

        self.config_display = QTextEdit()
        self.config_display.setReadOnly(True)
        self.config_display.setFont(QFont("Courier", 9))
        config_layout.addWidget(self.config_display)

        layout.addWidget(config_group)

        return widget

    def setup_status_updates(self):
        """Set up periodic status updates."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status_display)
        self.timer.start(1000)  # Update every second

        # Initial log message
        self.log_message("System initialized")
        self.update_config_display()

    def make_callback(self, attribute: str) -> Callable:
        """Create a callback function that updates the state and logs the change."""

        def callback(value):
            old_value = getattr(self.state, attribute)
            setattr(self.state, attribute, value)
            self.log_message(f"Changed {attribute}: {old_value} → {value}")
            self.update_config_display()

        return callback

    def toggle_log_drawer(self, checked):
        """Toggle the event log drawer based on checkbox state."""
        if not self.drawer:
            return

        # Only toggle if the checkbox state doesn't match the drawer state
        if checked != self.drawer.is_open:
            self.drawer.toggle()

    def keyboard_toggle_log(self):
        """Handle keyboard shortcut (Ctrl+L) for toggling the drawer."""
        if not self.drawer:
            return
        # Toggle the drawer and update checkbox to match
        self.drawer.toggle()
        self.log_toggle_button.setChecked(self.drawer.is_open)

    def log_message(self, message: str):
        """Add a message to the event log (now in the drawer)."""
        if hasattr(self, "drawer") and self.drawer:
            self.drawer.add_log_message(message)

    def update_status_display(self):
        """Update the status indicators."""
        # Simulate some changing values
        import random

        self.state.temperature = 23.5 + random.uniform(-0.5, 0.5)
        self.state.humidity = 45.0 + random.uniform(-2.0, 2.0)

        # Update the status labels (only if UI is ready)
        if self.temp_label is not None:
            self.temp_label.setText(f"Temperature: {self.state.temperature:.1f} °C")
        if self.humidity_label is not None:
            self.humidity_label.setText(f"Humidity: {self.state.humidity:.1f} %")
        if self.ready_label is not None:
            self.ready_label.setText(
                "System Ready: ✓ Ready" if self.state.system_ready else "System Ready: ✗ Not Ready"
            )

    def update_config_display(self):
        """Update the configuration display."""
        if self.config_display is None:
            return  # UI not ready yet
        config_dict = self.state.to_dict()
        config_json = json.dumps(config_dict, indent=2)
        self.config_display.setPlainText(config_json)

    def start_acquisition(self):
        """Start data acquisition."""
        self.log_message("Starting acquisition...")
        self.status_bar.showMessage("Acquiring...")

    def stop_acquisition(self):
        """Stop data acquisition."""
        self.log_message("Stopping acquisition")
        self.status_bar.showMessage("System Ready")

    def save_configuration(self):
        """Save current configuration."""
        self.log_message("Configuration saved")

    def load_configuration(self):
        """Load saved configuration."""
        self.log_message("Configuration loaded")

    def resizeEvent(self, a0):
        """Handle window resize to update drawer width."""
        super().resizeEvent(a0)
        if hasattr(self, "drawer") and self.drawer:
            # Update drawer width to 50% of new window width
            new_drawer_width = int(self.width() * 0.5)
            self.drawer.drawer_width = new_drawer_width
            self.drawer.setFixedWidth(new_drawer_width)

    def closeEvent(self, event):
        """Handle window close to clean up resources."""
        # Stop the status update timer
        if hasattr(self, "timer") and self.timer:
            self.timer.stop()

        event.accept()


if __name__ == "__main__":
    app = QApplication([])

    # Set application style
    app.setStyle("Fusion")

    window = MicroscopeControlInterface()
    window.show()

    app.exec()

"""Microscope Control Interface Example.

This example demonstrates a realistic microscope control interface built using
the vxl_qt primitives. It showcases how to create a proper UI application
with state management, status indicators, and organized control panels.
"""

import json
import random
from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from vxl_qt.ui.kit import DoubleSpinBox, Select, Text, Toggle


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
        self.event_log = None

        self._setup_ui()
        self._setup_status_updates()

    def _setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("ExaSPIM Microscope Control - vxl_qt Demo")
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget with main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main vertical layout for the entire window
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # Create top header
        header_layout = QHBoxLayout()
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Create controls and status panels
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        content_layout.addWidget(splitter)

        # Left panel - Controls
        controls_widget = self._create_controls_panel()
        splitter.addWidget(controls_widget)

        # Right panel - Status
        status_widget = self._create_status_panel()
        splitter.addWidget(status_widget)

        # Set splitter proportions
        splitter.setSizes([800, 400])

        main_layout.addWidget(content_widget)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("System Ready")

    def _create_controls_panel(self) -> QWidget:
        """Create the left panel with all control groups."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Title
        title = Text.title("Microscope Controls")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Experiment Info Group
        exp_group = self._create_experiment_group()
        layout.addWidget(exp_group)

        # Camera Controls Group
        camera_group = self._create_camera_group()
        layout.addWidget(camera_group)

        # Laser Controls Group
        laser_group = self._create_laser_group()
        layout.addWidget(laser_group)

        # Stage Controls Group
        stage_group = self._create_stage_group()
        layout.addWidget(stage_group)

        # Action Buttons
        buttons_group = self._create_action_buttons()
        layout.addWidget(buttons_group)

        layout.addStretch()
        return widget

    def _create_experiment_group(self) -> QGroupBox:
        """Create experiment information controls."""
        group = QGroupBox("Experiment Setup")
        form = QFormLayout(group)

        # Experiment Name
        self._experiment_name_input = QLineEdit(self.state.experiment_name)
        self._experiment_name_input.textChanged.connect(self._make_callback("experiment_name"))
        form.addRow("Experiment Name:", self._experiment_name_input)

        # Sample ID
        self._sample_id_input = QLineEdit(self.state.sample_id)
        self._sample_id_input.textChanged.connect(self._make_callback("sample_id"))
        form.addRow("Sample ID:", self._sample_id_input)

        # Objective
        self._objective_select = Select(
            options=["10x/0.3 NA", "20x/0.8 NA", "40x/0.9 NA", "63x/1.4 NA"],
            value=self.state.objective_lens,
        )
        self._objective_select.value_changed.connect(self._make_callback("objective_lens"))
        form.addRow("Objective:", self._objective_select)

        # Acquisition Mode
        self._mode_select = Select(
            options=["Single Image", "Time Series", "Z-Stack", "Tile Scan"],
            value=self.state.acquisition_mode,
        )
        self._mode_select.value_changed.connect(self._make_callback("acquisition_mode"))
        form.addRow("Acquisition Mode:", self._mode_select)

        return group

    def _create_camera_group(self) -> QGroupBox:
        """Create camera control panel."""
        group = QGroupBox("Camera Settings")
        form = QFormLayout(group)

        # Camera Enable
        self._camera_toggle = Toggle()
        self._camera_toggle.setChecked(self.state.camera_enabled)
        self._camera_toggle.toggled.connect(self._make_callback("camera_enabled"))
        form.addRow("Camera Enable:", self._camera_toggle)

        # Exposure
        self._exposure_spinbox = DoubleSpinBox(
            value=self.state.exposure_time,
            min_val=0.001,
            max_val=10.0,
            decimals=3,
        )
        self._exposure_spinbox.setSuffix(" s")
        self._exposure_spinbox.valueChanged.connect(self._make_callback("exposure_time"))
        form.addRow("Exposure:", self._exposure_spinbox)

        # Gain
        self._gain_spinbox = DoubleSpinBox(
            value=float(self.state.gain),
            min_val=1.0,
            max_val=1000.0,
            decimals=0,
        )
        self._gain_spinbox.valueChanged.connect(lambda v: self._make_callback("gain")(int(v)))
        form.addRow("Gain:", self._gain_spinbox)

        # Binning
        self._binning_select = Select(
            options=["1x1", "2x2", "4x4"],
            value=self.state.binning,
        )
        self._binning_select.value_changed.connect(self._make_callback("binning"))
        form.addRow("Binning:", self._binning_select)

        return group

    def _create_laser_group(self) -> QGroupBox:
        """Create laser control panel."""
        group = QGroupBox("Laser Controls")
        layout = QVBoxLayout(group)

        # 405nm Laser
        laser_405_layout = QHBoxLayout()
        laser_405_layout.addWidget(Text("405nm Enable:"))
        self._laser_405_toggle = Toggle()
        self._laser_405_toggle.setChecked(self.state.laser_405_enabled)
        self._laser_405_toggle.toggled.connect(self._make_callback("laser_405_enabled"))
        laser_405_layout.addWidget(self._laser_405_toggle)
        laser_405_layout.addWidget(Text("Power (mW):"))
        self._laser_405_power = DoubleSpinBox(value=self.state.laser_405_power, min_val=0.0, max_val=50.0, decimals=1)
        self._laser_405_power.valueChanged.connect(self._make_callback("laser_405_power"))
        laser_405_layout.addWidget(self._laser_405_power)
        laser_405_layout.addStretch()
        layout.addLayout(laser_405_layout)

        # 488nm Laser
        laser_488_layout = QHBoxLayout()
        laser_488_layout.addWidget(Text("488nm Enable:"))
        self._laser_488_toggle = Toggle()
        self._laser_488_toggle.setChecked(self.state.laser_488_enabled)
        self._laser_488_toggle.toggled.connect(self._make_callback("laser_488_enabled"))
        laser_488_layout.addWidget(self._laser_488_toggle)
        laser_488_layout.addWidget(Text("Power (mW):"))
        self._laser_488_power = DoubleSpinBox(value=self.state.laser_488_power, min_val=0.0, max_val=100.0, decimals=1)
        self._laser_488_power.valueChanged.connect(self._make_callback("laser_488_power"))
        laser_488_layout.addWidget(self._laser_488_power)
        laser_488_layout.addStretch()
        layout.addLayout(laser_488_layout)

        # 561nm Laser
        laser_561_layout = QHBoxLayout()
        laser_561_layout.addWidget(Text("561nm Enable:"))
        self._laser_561_toggle = Toggle()
        self._laser_561_toggle.setChecked(self.state.laser_561_enabled)
        self._laser_561_toggle.toggled.connect(self._make_callback("laser_561_enabled"))
        laser_561_layout.addWidget(self._laser_561_toggle)
        laser_561_layout.addWidget(Text("Power (mW):"))
        self._laser_561_power = DoubleSpinBox(value=self.state.laser_561_power, min_val=0.0, max_val=75.0, decimals=1)
        self._laser_561_power.valueChanged.connect(self._make_callback("laser_561_power"))
        laser_561_layout.addWidget(self._laser_561_power)
        laser_561_layout.addStretch()
        layout.addLayout(laser_561_layout)

        return group

    def _create_stage_group(self) -> QGroupBox:
        """Create stage control panel."""
        group = QGroupBox("Stage Position")
        grid = QGridLayout(group)

        # X position
        grid.addWidget(Text("X (μm):"), 0, 0)
        self._stage_x = DoubleSpinBox(value=self.state.stage_x, min_val=0.0, max_val=25000.0, decimals=1)
        self._stage_x.valueChanged.connect(self._make_callback("stage_x"))
        grid.addWidget(self._stage_x, 0, 1)

        # Y position
        grid.addWidget(Text("Y (μm):"), 0, 2)
        self._stage_y = DoubleSpinBox(value=self.state.stage_y, min_val=0.0, max_val=25000.0, decimals=1)
        self._stage_y.valueChanged.connect(self._make_callback("stage_y"))
        grid.addWidget(self._stage_y, 0, 3)

        # Z position
        grid.addWidget(Text("Z (μm):"), 1, 0)
        self._stage_z = DoubleSpinBox(value=self.state.stage_z, min_val=0.0, max_val=1000.0, decimals=1)
        self._stage_z.valueChanged.connect(self._make_callback("stage_z"))
        grid.addWidget(self._stage_z, 1, 1)

        # Step size
        grid.addWidget(Text("Step Size (μm):"), 1, 2)
        self._stage_step = DoubleSpinBox(value=self.state.stage_step_size, min_val=0.1, max_val=1000.0, decimals=1)
        self._stage_step.valueChanged.connect(self._make_callback("stage_step_size"))
        grid.addWidget(self._stage_step, 1, 3)

        return group

    def _create_action_buttons(self) -> QGroupBox:
        """Create action buttons group."""
        group = QGroupBox("Actions")
        layout = QHBoxLayout(group)

        start_btn = QPushButton("Start Acquisition")
        start_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px; }",
        )
        start_btn.clicked.connect(self._start_acquisition)

        stop_btn = QPushButton("Stop")
        stop_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px; }",
        )
        stop_btn.clicked.connect(self._stop_acquisition)

        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self._save_configuration)

        load_btn = QPushButton("Load Config")
        load_btn.clicked.connect(self._load_configuration)

        layout.addWidget(start_btn)
        layout.addWidget(stop_btn)
        layout.addWidget(save_btn)
        layout.addWidget(load_btn)

        return group

    def _create_status_panel(self) -> QWidget:
        """Create the right panel with status information and event log."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status indicators
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout(status_group)

        self.temp_label = Text(f"Temperature: {self.state.temperature:.1f} °C")
        self.humidity_label = Text(f"Humidity: {self.state.humidity:.1f} %")
        self.ready_label = Text("System Ready: ✓ Ready" if self.state.system_ready else "System Ready: ✗ Not Ready")

        status_layout.addWidget(self.temp_label)
        status_layout.addWidget(self.humidity_label)
        status_layout.addWidget(self.ready_label)
        layout.addWidget(status_group)

        # Create vertical splitter for config display and event log
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(vertical_splitter)

        # Current configuration display
        config_group = QGroupBox("Current Configuration")
        config_layout = QVBoxLayout(config_group)

        self.config_display = QTextEdit()
        self.config_display.setReadOnly(True)
        self.config_display.setFont(QFont("Courier", 9))
        config_layout.addWidget(self.config_display)

        vertical_splitter.addWidget(config_group)

        # Event log display
        log_group = QGroupBox("Event Log")
        log_layout = QVBoxLayout(log_group)

        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setFont(QFont("Courier", 9))
        self.event_log.setStyleSheet("""
            QTextEdit {
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
            QScrollBar:vertical {
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: palette(button);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: palette(highlight);
            }
        """)
        log_layout.addWidget(self.event_log)

        vertical_splitter.addWidget(log_group)

        # Set initial splitter sizes - config display gets 60%, event log gets 40%
        vertical_splitter.setSizes([300, 200])

        return widget

    def _setup_status_updates(self):
        """Set up periodic status updates."""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status_display)
        self.timer.start(1000)  # Update every second

        # Initial log message
        self._log_message("System initialized")
        self._update_config_display()

    def _make_callback(self, attribute: str) -> Callable:
        """Create a callback function that updates the state and logs the change."""

        def callback(value):
            old_value = getattr(self.state, attribute)
            setattr(self.state, attribute, value)
            self._log_message(f"Changed {attribute}: {old_value} → {value}")
            self._update_config_display()

        return callback

    def _log_message(self, message: str):
        """Add a message to the event log."""
        if self.event_log is not None:
            timestamp = datetime.now(UTC).strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}"
            self.event_log.append(log_entry)

    def _update_status_display(self):
        """Update the status indicators."""
        # Simulate some changing values

        self.state.temperature = 23.5 + random.uniform(-0.5, 0.5)
        self.state.humidity = 45.0 + random.uniform(-2.0, 2.0)

        # Update the status labels (only if UI is ready)
        if self.temp_label is not None:
            self.temp_label.setText(f"Temperature: {self.state.temperature:.1f} °C")
        if self.humidity_label is not None:
            self.humidity_label.setText(f"Humidity: {self.state.humidity:.1f} %")
        if self.ready_label is not None:
            self.ready_label.setText(
                "System Ready: ✓ Ready" if self.state.system_ready else "System Ready: ✗ Not Ready",
            )

    def _update_config_display(self):
        """Update the configuration display."""
        if self.config_display is None:
            return  # UI not ready yet
        config_dict = self.state.to_dict()
        config_json = json.dumps(config_dict, indent=2)
        self.config_display.setPlainText(config_json)

    def _start_acquisition(self):
        """Start data acquisition."""
        self._log_message("Starting acquisition...")
        self.status_bar.showMessage("Acquiring...")

    def _stop_acquisition(self):
        """Stop data acquisition."""
        self._log_message("Stopping acquisition")
        self.status_bar.showMessage("System Ready")

    def _save_configuration(self):
        """Save current configuration."""
        self._log_message("Configuration saved")

    def _load_configuration(self):
        """Load saved configuration."""
        self._log_message("Configuration loaded")

    def closeEvent(self, event) -> None:
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

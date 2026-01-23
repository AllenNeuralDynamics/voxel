"""Hardware control demo using voxel_qt primitives.

This demonstrates how to use SpinBox/DoubleSpinBox with mock hardware,
using Qt's signal-based architecture rather than getter/setter bindings.
"""

import random
from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget
from rich import print
from voxel_qt.ui.primitives.input import DoubleSpinBox, SpinBox


class MockHardware:
    """Simulates a simple hardware device."""

    def __init__(self):
        self._position = 42  # Starting position (int)
        self._target_temperature = 25.0  # Starting target temperature (float)
        self._voltage = 3.3  # Starting voltage (float)

    def get_position(self) -> int:
        print(f"[blue]Reading position from hardware: {self._position}[/blue]")
        return self._position

    def set_position(self, position: int) -> None:
        print(f"[green]Setting hardware position to: {position}[/green]")
        self._position = position

    def get_voltage(self) -> float:
        print(f"[blue]Reading voltage from hardware: {self._voltage:.2f}V[/blue]")
        return self._voltage

    def set_voltage(self, voltage: float) -> None:
        print(f"[green]Setting hardware voltage to: {voltage:.2f}V[/green]")
        # Simulate some settling error
        self._voltage = round(voltage + (random.random() * 0.2 - 0.1), 2)

    @property
    def temperature(self):
        print(f"[blue]Reading temperature from hardware: {self._target_temperature}[/blue]")
        return self._target_temperature + (random.random() * 2 - 1)

    @property
    def target_temperature(self):
        print(f"[blue]Reading target temperature from hardware: {self._target_temperature}[/blue]")
        return self._target_temperature

    @target_temperature.setter
    def target_temperature(self, value: float):
        print(f"[green]Setting hardware target temperature to: {value:.1f}[/green]")
        self._target_temperature = round(value + (random.random() * 4 - 2), 2)  # Simulate some error


class VoltageWidget(QGroupBox):
    """Widget for controlling hardware voltage using DoubleSpinBox."""

    def __init__(self, getter: Callable[[], float], setter: Callable[[float], None], parent=None):
        super().__init__("Voltage Control", parent)
        self._getter = getter
        self._setter = setter
        self._setup_ui()

    def _setup_ui(self):
        """Create voltage control UI with DoubleSpinBox."""
        layout = QVBoxLayout(self)

        # Use DoubleSpinBox for voltage control
        self.voltage_spinbox = DoubleSpinBox(
            value=self._getter(),
            min_val=0.0,
            max_val=10.0,
            decimals=2,
            step=0.1,
        )
        self.voltage_spinbox.setSuffix("V")

        # Display label that shows current voltage
        self.voltage_label = QLabel(f"Current Voltage: {self.voltage_spinbox.value():.2f}V")

        # Connect the spinbox to the setter and update display
        self.voltage_spinbox.valueChanged.connect(self._on_value_changed)

        layout.addWidget(QLabel("Set Voltage:"))
        layout.addWidget(self.voltage_spinbox)
        layout.addWidget(self.voltage_label)

    def _on_value_changed(self, value: float):
        """Handle value change from spinbox."""
        self._setter(value)
        self.voltage_label.setText(f"Current Voltage: {value:.2f}V")

    def refresh(self):
        """Refresh voltage from hardware."""
        try:
            value = self._getter()
            self.voltage_spinbox.blockSignals(True)
            self.voltage_spinbox.setValue(value)
            self.voltage_spinbox.blockSignals(False)
            self.voltage_label.setText(f"Current Voltage: {value:.2f}V")
        except Exception as e:
            print(f"[red]Error refreshing voltage: {e}[/red]")


class PositionWidget(QGroupBox):
    """Widget for controlling hardware position using SpinBox."""

    def __init__(self, getter: Callable[[], int], setter: Callable[[int], None], parent=None):
        super().__init__("Position Control", parent)
        self._getter = getter
        self._setter = setter
        self._setup_ui()

    def _setup_ui(self):
        """Create position control UI with SpinBox."""
        layout = QVBoxLayout(self)

        # Use SpinBox for position control
        self.pos_spinbox = SpinBox(
            value=self._getter(),
            min_val=0,
            max_val=1000,
        )

        # Display label that shows current position
        self.pos_label = QLabel(f"Current Position: {self.pos_spinbox.value()}")

        # Connect the spinbox to the setter and update display
        self.pos_spinbox.valueChanged.connect(self._on_value_changed)

        layout.addWidget(QLabel("Set Position:"))
        layout.addWidget(self.pos_spinbox)
        layout.addWidget(self.pos_label)

    def _on_value_changed(self, value: int):
        """Handle value change from spinbox."""
        self._setter(value)
        self.pos_label.setText(f"Current Position: {value}")

    def refresh(self):
        """Refresh position from hardware."""
        try:
            value = self._getter()
            self.pos_spinbox.blockSignals(True)
            self.pos_spinbox.setValue(value)
            self.pos_spinbox.blockSignals(False)
            self.pos_label.setText(f"Current Position: {value}")
        except Exception as e:
            print(f"[red]Error refreshing position: {e}[/red]")


class TemperatureWidget(QGroupBox):
    """Widget for monitoring and controlling temperature using DoubleSpinBox."""

    def __init__(self, hardware, parent=None):
        super().__init__("Temperature Control", parent)
        self.hardware = hardware
        self._setup_ui()

    def _setup_ui(self):
        """Create temperature control UI with DoubleSpinBox."""
        layout = QVBoxLayout(self)

        # Use DoubleSpinBox for target temperature control
        self.target_spinbox = DoubleSpinBox(
            value=self.hardware.target_temperature,
            min_val=0.0,
            max_val=100.0,
            decimals=1,
        )
        self.target_spinbox.setSuffix("°C")

        # Display label for target temperature
        self.target_label = QLabel(f"Target: {self.target_spinbox.value():.1f}°C")

        # Actual temperature display (using polling with QTimer)
        self.actual_temp_label = QLabel(f"Actual: {self.hardware.temperature:.1f}°C")

        # Connect the spinbox to update target
        self.target_spinbox.valueChanged.connect(self._on_target_changed)

        # Setup polling timer for actual temperature
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._update_actual_temperature)
        self._poll_timer.start(1000)  # Poll every second

        layout.addWidget(QLabel("Set Target Temperature:"))
        layout.addWidget(self.target_spinbox)
        layout.addWidget(self.target_label)
        layout.addWidget(self.actual_temp_label)

    def _on_target_changed(self, value: float):
        """Handle target temperature change."""
        self.hardware.target_temperature = value
        self.target_label.setText(f"Target: {value:.1f}°C")

    def _update_actual_temperature(self):
        """Update actual temperature display from hardware."""
        actual = self.hardware.temperature
        self.actual_temp_label.setText(f"Actual: {actual:.1f}°C")

    def refresh(self):
        """Refresh target temperature from hardware."""
        try:
            value = self.hardware.target_temperature
            self.target_spinbox.blockSignals(True)
            self.target_spinbox.setValue(value)
            self.target_spinbox.blockSignals(False)
            self.target_label.setText(f"Target: {value:.1f}°C")
            self._update_actual_temperature()
        except Exception as e:
            print(f"[red]Error refreshing target temperature: {e}[/red]")


class MockHardwareWidget(QWidget):
    """Composite widget that manages all hardware controls."""

    def __init__(self, hardware: MockHardware, parent=None):
        super().__init__(parent)
        self.hardware = hardware
        self._setup_ui()

    def _setup_ui(self):
        """Create the composite UI with child widgets."""
        layout = QVBoxLayout(self)

        # Create child widgets
        self.position_widget = PositionWidget(getter=self.hardware.get_position, setter=self.hardware.set_position)
        self.voltage_widget = VoltageWidget(getter=self.hardware.get_voltage, setter=self.hardware.set_voltage)
        self.temperature_widget = TemperatureWidget(self.hardware)

        # Global refresh button
        self.refresh_all_btn = QPushButton("Refresh All")
        self.refresh_all_btn.clicked.connect(self.refresh_all)

        layout.addWidget(self.position_widget)
        layout.addWidget(self.voltage_widget)
        layout.addWidget(self.temperature_widget)
        layout.addWidget(self.refresh_all_btn)

    def refresh_all(self):
        """Refresh all hardware values."""
        self.position_widget.refresh()
        self.voltage_widget.refresh()
        self.temperature_widget.refresh()


# Example usage
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication

    print("[cyan]Hardware control demo using voxel_qt primitives[/cyan]")
    print("[cyan]- SpinBox: Integer values (position)[/cyan]")
    print("[cyan]- DoubleSpinBox: Float values (voltage, temperature)[/cyan]")
    print()

    app = QApplication(sys.argv)

    # Create mock hardware
    hardware = MockHardware()

    # Create the composite hardware widget
    widget = MockHardwareWidget(hardware)
    widget.setWindowTitle("Hardware Control - voxel_qt Primitives Demo")
    widget.resize(400, 500)
    widget.show()

    print("[yellow]Try changing position (int), voltage (float), and temperature (float) values![/yellow]")
    print("[yellow]Watch the console for hardware interactions.[/yellow]")

    sys.exit(app.exec())

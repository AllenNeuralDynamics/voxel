import random
from collections.abc import Callable

from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget
from rich import print
from spim_widgets.ui.input.label import LiveValueLabel
from spim_widgets.ui.input.number import VNumberInput


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
        # Simulate hardware delay without blocking UI thread
        # In real hardware, this would be a non-blocking operation
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
    """Widget for controlling hardware voltage using VNumberInput[float]."""

    def __init__(self, getter: Callable[[], float], setter: Callable[[float], None], parent=None):
        super().__init__("Voltage Control", parent)
        self.setup_ui(getter, setter)

    def setup_ui(self, getter: Callable[[], float], setter: Callable[[float], None]):
        """Create voltage control UI with VNumberInput[float]."""
        layout = QVBoxLayout(self)

        # Use VNumberInput[float] for voltage control
        self.voltage_spinbox: VNumberInput[float] = VNumberInput[float](
            getter=getter,
            onchange=setter,
            debounce_delay=300,  # Debounce voltage changes
            watch_interval=None,  # No continuous monitoring for voltage
            parent=self,
        )

        # Configure for voltage (0-10V range, 0.1V steps, 2 decimal places)
        self.voltage_spinbox.setRange(0.0, 10.0)
        self.voltage_spinbox.setSingleStep(0.1)
        self.voltage_spinbox.setDecimals(2)
        self.voltage_spinbox.setSuffix("V")

        # Display label that shows current voltage
        self.voltage_label = QLabel(f"Current Voltage: {self.voltage_spinbox.value:.2f}V")

        # Connect the VNumberInput to update our display label
        self.voltage_spinbox._binding.value_changed.connect(self.update_display)

        layout.addWidget(QLabel("Set Voltage:"))
        layout.addWidget(self.voltage_spinbox.widget)  # Use .widget property for layout
        layout.addWidget(self.voltage_label)

    def update_display(self, value: float):
        """Update voltage display when hardware value changes."""
        self.voltage_label.setText(f"Current Voltage: {value:.2f}V")

    def refresh(self):
        """Refresh voltage from hardware."""
        try:
            self.voltage_spinbox.refresh()
            # The spinbox will automatically update its display and emit signals
        except Exception as e:
            print(f"[red]Error refreshing voltage: {e}[/red]")


class PositionWidget(QGroupBox):
    """Widget for controlling hardware position using ValueBoundSpinBox."""

    def __init__(self, getter: Callable[[], int], setter: Callable[[int], None], parent=None):
        super().__init__("Position Control", parent)
        self.setup_ui(getter, setter)

    def setup_ui(self, getter: Callable[[], int], setter: Callable[[int], None]):
        """Create position control UI with VNumberInput[int]."""
        layout = QVBoxLayout(self)

        # Use VNumberInput[int] for position control
        self.pos_spinbox: VNumberInput[int] = VNumberInput[int](
            getter=getter,
            onchange=setter,
            debounce_delay=300,  # Debounce position changes
            watch_interval=None,  # No continuous monitoring for position
            parent=self,
        )

        # Display label that shows current position
        self.pos_label = QLabel(f"Current Position: {self.pos_spinbox.value}")

        # Connect the VNumberInput to update our display label
        self.pos_spinbox._binding.value_changed.connect(self.update_display)

        layout.addWidget(QLabel("Set Position:"))
        layout.addWidget(self.pos_spinbox.widget)  # Use .widget property for layout
        layout.addWidget(self.pos_label)

    def update_display(self, value):
        """Update position display when hardware value changes."""
        self.pos_label.setText(f"Current Position: {value}")

    def refresh(self):
        """Refresh position from hardware."""
        try:
            self.pos_spinbox.refresh()
            # The spinbox will automatically update its display and emit signals
        except Exception as e:
            print(f"[red]Error refreshing position: {e}[/red]")


class TemperatureWidget(QGroupBox):
    """Widget for monitoring and controlling temperature using ValueBoundSpinBox."""

    def __init__(self, hardware, parent=None):
        super().__init__("Temperature Control", parent)
        self.hardware = hardware
        self.setup_ui()

    def setup_ui(self):
        """Create temperature control UI with VNumberInput[float]."""
        layout = QVBoxLayout(self)

        # Use VNumberInput[float] for target temperature control
        self.target_spinbox: VNumberInput[float] = VNumberInput[float](
            getter=lambda: self.hardware.target_temperature,
            onchange=lambda x: setattr(self.hardware, "target_temperature", x),
            debounce_delay=300,  # Debounce temperature changes
            watch_interval=1000,  # Continuous monitoring needed for target temp
            parent=self,
        )
        self.target_spinbox.setRange(0.0, 100.0)  # Use forwarded method
        self.target_spinbox.setDecimals(1)  # 1 decimal place for temperature
        self.target_spinbox.setSuffix("°C")  # Use forwarded method

        # Display label for target temperature
        self.target_label = QLabel(f"Target: {self.target_spinbox.value}°C")

        # Actual temperature display using LiveValueLabel (polling)
        self.actual_temp_widget = LiveValueLabel(
            getter=lambda: self.hardware.temperature,
            prefix="Actual: ",
            suffix="°C",
            format_func=lambda x: f"{x:.1f}",
            poll_interval=1000,
        )

        # Connect the VNumberInput to update our display label
        self.target_spinbox._binding.value_changed.connect(self.update_target_display)

        layout.addWidget(QLabel("Set Target Temperature:"))
        layout.addWidget(self.target_spinbox.widget)  # Use .widget property for layout
        layout.addWidget(self.target_label)
        layout.addWidget(self.actual_temp_widget.widget)  # Use .widget property for layout

    def update_target_display(self, value):
        """Update target temperature display."""
        self.target_label.setText(f"Target: {value}°C")

    def refresh(self):
        """Refresh target temperature from hardware."""
        try:
            self.target_spinbox.refresh()
            # The spinbox will automatically update its display and emit signals

            # Also refresh the actual temperature display
            self.actual_temp_widget.refresh()
        except Exception as e:
            print(f"[red]Error refreshing target temperature: {e}[/red]")


class MockHardwareWidget(QWidget):
    """Composite widget that manages all hardware controls."""

    def __init__(self, hardware: MockHardware, parent=None):
        super().__init__(parent)
        self.hardware = hardware
        self.setup_ui()

    def setup_ui(self):
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
    from rich import print

    # Demonstrate preset usage (uncomment to try different configurations)
    print("[cyan]Available binding presets:[/cyan]")
    print("[cyan]- BindingPresets.FAST_HARDWARE: Quick response, minimal delays[/cyan]")
    print("[cyan]- BindingPresets.SLOW_HARDWARE: Conservative timing for slow devices[/cyan]")
    print("[cyan]- BindingPresets.MONITORED: Includes continuous polling[/cyan]")
    print("[cyan]- BindingPresets.PRECISION: Extended delays for high-precision instruments[/cyan]")
    print("[cyan]- BindingPresets.RESPONSIVE: Balanced for UI responsiveness[/cyan]")
    print()

    print("[cyan]Generic VNumberInput examples:[/cyan]")
    print("[cyan]- VNumberInput[int]: Creates QSpinBox for integer values[/cyan]")
    print("[cyan]- VNumberInput[float]: Creates QDoubleSpinBox for float values[/cyan]")
    print()

    # Example of using presets with typed spinboxes:
    # int_spinbox = VNumberInput[int](int_getter, int_setter, **BindingPresets.FAST_HARDWARE)
    # float_spinbox = VNumberInput[float](float_getter, float_setter, **BindingPresets.PRECISION)

    app = QApplication(sys.argv)

    # Create mock hardware
    hardware = MockHardware()

    # Create the composite hardware widget
    widget = MockHardwareWidget(hardware)
    widget.setWindowTitle("Generic Hardware Control Widget - Int & Float SpinBoxes")
    widget.resize(400, 500)
    widget.show()

    print("[yellow]Try changing position (int), voltage (float), and temperature (float) values![/yellow]")
    print("[yellow]Notice how position uses QSpinBox and voltage/temperature use QDoubleSpinBox![/yellow]")
    print("[yellow]Watch the console for hardware interactions.[/yellow]")

    sys.exit(app.exec())

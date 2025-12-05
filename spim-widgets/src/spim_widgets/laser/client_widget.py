"""Laser widget using DeviceClient."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from pyrig.device import DeviceClient
from pyrig.device.base import PropsResponse
from spim_widgets.base import DeviceClientAdapter, DeviceClientWidget
from spim_widgets.laser.client_adapter import LaserClientAdapter
from spim_widgets.laser.power import PowerSetpointInput
from spim_widgets.laser.utils import (
    darken_color,
    lighten_color,
    rgb_to_hex,
    wavelength_to_rgb,
)
from spim_widgets.ui.chip import Chip
from spim_widgets.ui.input.binding import FieldBinder


class WavelengthChip(Chip):
    """Chip displaying laser wavelength with color coding."""

    def __init__(self, wavelength: int, parent=None) -> None:
        # Get the base RGB color for the wavelength
        r_float, g_float, b_float = wavelength_to_rgb(wavelength)

        # Scale to 0-255 and convert to int
        r, g, b = int(r_float * 255), int(g_float * 255), int(b_float * 255)

        # Create light and dark shades
        light_rgb = lighten_color(r, g, b)
        dark_rgb = darken_color(r, g, b)

        # Convert to hex
        bg_color_hex = rgb_to_hex(*light_rgb)
        border_color_hex = rgb_to_hex(*dark_rgb)

        super().__init__(
            text=f"{wavelength} nm",
            color=bg_color_hex,
            border_color=border_color_hex,
            parent=parent,
        )


class LaserClientWidget(DeviceClientWidget):
    """Laser control widget using DeviceClient.

    Features:
    - Wavelength display
    - Power setpoint control with slider
    - Enable/disable status
    - Temperature display
    - Automatic property updates via subscription
    """

    def __init__(
        self,
        client: DeviceClient,
        parent=None,
        color: str = "#18181b",
        border_color: str = "#3e3e44",
        border_radius: int = 16,
    ) -> None:
        self._color = color
        self._border_color = border_color
        self._border_radius = border_radius
        self._wavelength = 488  # Default, will be updated from properties
        self._is_enabled = False
        self._temperature_c = None

        super().__init__(client, parent)

        self.setFixedWidth(560)
        self.setFixedHeight(220)

        # Set size policy to prevent expansion
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _create_adapter(self, client: DeviceClient) -> DeviceClientAdapter:
        """Create laser-specific adapter."""
        return LaserClientAdapter(client, parent=self)

    def _setup_ui(self) -> None:
        """Setup the laser widget UI."""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)

        # Header with wavelength and enable status
        header_layout = QHBoxLayout()

        self._wavelength_chip = WavelengthChip(wavelength=self._wavelength)
        header_layout.addWidget(self._wavelength_chip)

        self._name_label = QLabel(self.client.uid)
        header_layout.addWidget(self._name_label)

        header_layout.addStretch()

        # Enable/Disable buttons
        self._enable_button = QPushButton("Enable")
        self._enable_button.setFixedWidth(80)
        self._enable_button.clicked.connect(self._on_enable_clicked)
        header_layout.addWidget(self._enable_button)

        self._disable_button = QPushButton("Disable")
        self._disable_button.setFixedWidth(80)
        self._disable_button.clicked.connect(self._on_disable_clicked)
        header_layout.addWidget(self._disable_button)

        self._enable_chip = Chip(text="OFF", color="#666666", border_color="#444444")
        self._enable_chip.label.setAlignment(Qt.AlignmentFlag.AlignRight)
        header_layout.addWidget(self._enable_chip)

        main_layout.addLayout(header_layout)

        # Power control
        self._power_binder = FieldBinder[float, float](
            writer=lambda v: self.adapter.setPower(float(v)),
            debounce_ms=150,
            parent=self,
        )

        self._power_input = PowerSetpointInput(
            binding=self._power_binder,
            wavelength=self._wavelength,
        )
        main_layout.addWidget(self._power_input)

        # Footer with temperature
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)

        self._temp_chip = Chip(text="TEMP --°C", color="#3e3e44", border_color="#29292c")
        self._temp_chip.label.setFont(QFont("Menlo", 12, QFont.Weight.Normal))
        footer_layout.addWidget(self._temp_chip)
        footer_layout.addStretch()

        main_layout.addLayout(footer_layout)

    def _on_properties_changed(self, props: PropsResponse) -> None:
        """Handle property updates from device."""
        # Update wavelength (shouldn't change, but good to have)
        if "wavelength" in props.res:
            wavelength = props.res["wavelength"].value
            if wavelength != self._wavelength:
                self._wavelength = wavelength
                self._wavelength_chip = WavelengthChip(wavelength)

        # Update power setpoint
        if "power_setpoint_mw" in props.res:
            prop = props.res["power_setpoint_mw"]
            power = prop.value
            self._power_binder.update(power)

            # Update range if metadata is available
            if prop.min_val is not None and prop.max_val is not None and prop.step is not None:
                self._power_input.update_range(
                    min_value=float(prop.min_val),
                    max_value=float(prop.max_val),
                    step=float(prop.step),
                )

        # Update enable status
        if "is_enabled" in props.res:
            self._is_enabled = props.res["is_enabled"].value
            self._update_enable_display()

        # Update temperature
        if "temperature_c" in props.res:
            self._temperature_c = props.res["temperature_c"].value
            self._update_temperature_display()

    def _update_enable_display(self) -> None:
        """Update the enable status chip and button states."""
        if self._is_enabled:
            self._enable_chip.setText("ON")
            self._enable_chip.setColor("#419044", "#245D27")
            self._enable_button.setEnabled(False)
            self._disable_button.setEnabled(True)
        else:
            self._enable_chip.setText("OFF")
            self._enable_chip.setColor("#666666", "#444444")
            self._enable_button.setEnabled(True)
            self._disable_button.setEnabled(False)

    def _update_temperature_display(self) -> None:
        """Update the temperature chip."""
        if self._temperature_c is not None:
            self._temp_chip.setText(f"TEMP {self._temperature_c:.2f}°C")
        else:
            self._temp_chip.setText("TEMP --°C")

    def _on_enable_clicked(self) -> None:
        """Handle enable button click."""
        import asyncio

        asyncio.create_task(self.adapter.enable())

    def _on_disable_clicked(self) -> None:
        """Handle disable button click."""
        import asyncio

        asyncio.create_task(self.adapter.disable())

    def paintEvent(self, event):
        """Custom paint event for rounded border."""
        from PySide6.QtGui import QBrush, QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        brush = QBrush(QColor(self._color))
        pen = QPen(QColor(self._border_color))
        pen.setWidth(2)
        painter.setBrush(brush)
        painter.setPen(pen)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, self._border_radius, self._border_radius)

        super().paintEvent(event)

    @property
    def adapter(self) -> LaserClientAdapter:
        """Access the laser adapter with proper typing."""
        return self._adapter  # type: ignore

# from PySide6.QtCore import Qt
# from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPaintEvent, QPen
# from PySide6.QtWidgets import (
#     QHBoxLayout,
#     QLabel,
#     QVBoxLayout,
#     QWidget,
# )
# from voxel.devices.descriptions import generate_ui_label
# from voxel.devices.laser.agent import LaserAgent

# from spim_widgets.laser.adapter import QtLaserAdapter
# from spim_widgets.laser.power import PowerSetpointInput
# from spim_widgets.laser.utils import (
#     darken_color,
#     lighten_color,
#     rgb_to_hex,
#     wavelength_to_rgb,
# )
# from spim_widgets.ui.chip import Chip


# class WavelengthChip(Chip):
#     def __init__(self, wavelength: int, parent: QWidget | None = None) -> None:
#         # Get the base RGB color for the wavelength
#         r_float, g_float, b_float = wavelength_to_rgb(wavelength)

#         # Scale to 0-255 and convert to int
#         r, g, b = int(r_float * 255), int(g_float * 255), int(b_float * 255)

#         # Create light and dark shades
#         light_rgb = lighten_color(r, g, b)
#         dark_rgb = darken_color(r, g, b)

#         # Convert to hex
#         bg_color_hex = rgb_to_hex(*light_rgb)
#         border_color_hex = rgb_to_hex(*dark_rgb)

#         super().__init__(text=f"{wavelength} nm", color=bg_color_hex, border_color=border_color_hex, parent=parent)


# class LaserWidget(QWidget):
#     def __init__(
#         self, agent: LaserAgent, color: str = "#18181b", border_color: str = "#3e3e44", border_radius: int = 16
#     ) -> None:
#         super().__init__()
#         self.agent = agent
#         self.adapter = QtLaserAdapter(agent)
#         self._input = PowerSetpointInput(binding=self.adapter.power, wavelength=agent.laser.wavelength)

#         self._color = color
#         self._border_color = border_color
#         self._border_radius = border_radius

#         self.setFixedWidth(560)
#         self.setMinimumHeight(180)

#         main_layout = QVBoxLayout()
#         main_layout.setContentsMargins(10, 10, 10, 10)
#         self.setLayout(main_layout)

#         # Start -- Header Layout
#         header_layout = QHBoxLayout()
#         wavelength_chip = WavelengthChip(wavelength=self.agent.laser.wavelength)
#         header_layout.addWidget(wavelength_chip)
#         label = QLabel(f"{generate_ui_label(self.agent.uid)}")
#         header_layout.addWidget(label)
#         header_layout.addStretch()
#         enable_chip = Chip(text="ON", color="#419044", border_color="#245D27")
#         enable_chip.label.setAlignment(Qt.AlignmentFlag.AlignRight)
#         header_layout.addWidget(enable_chip)
#         main_layout.addLayout(header_layout)
#         # End -- Header Layout

#         # Add the power input below
#         main_layout.addWidget(self._input)

#         # Start -- Footer Layout
#         footer_layout = QHBoxLayout()
#         footer_layout.setContentsMargins(0, 0, 0, 0)
#         temp_chip = Chip(text="TEMP 25.02 °C", color="#3e3e44", border_color="#29292c")
#         temp_chip.label.setFont(QFont("Menlo", 12, QFont.Weight.Normal))
#         footer_layout.addWidget(temp_chip)
#         footer_layout.addStretch()
#         main_layout.addLayout(footer_layout)
#         # End -- Footer Layout

#     def paintEvent(self, event: QPaintEvent):
#         painter = QPainter(self)
#         painter.setRenderHint(QPainter.RenderHint.Antialiasing)

#         brush = QBrush(QColor(self._color))
#         pen = QPen(QColor(self._border_color))
#         pen.setWidth(2)  # Make border more visible
#         painter.setBrush(brush)
#         painter.setPen(pen)

#         rect = self.rect().adjusted(1, 1, -1, -1)  # Adjust for pen width
#         painter.drawRoundedRect(rect, self._border_radius, self._border_radius)

#         super().paintEvent(event)

#     def set_style(self, color: str | None = None, border_color: str | None = None, border_radius: int | None = None):
#         if color:
#             self._color = color
#         if border_color:
#             self._border_color = border_color
#         if border_radius is not None:
#             self._border_radius = border_radius
#         self.update()

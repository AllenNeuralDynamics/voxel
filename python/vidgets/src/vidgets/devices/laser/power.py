from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QSlider, QVBoxLayout, QWidget
from vidgets.devices.laser.utils import rgb_to_css_string, wavelength_to_rgb

if TYPE_CHECKING:
    from vidgets.devices.laser.adapter import FieldBinder

    from voxel.utils.descriptors.deliminated import DeliminatedFloat


class PowerSetpointInput(QWidget):
    def __init__(
        self,
        binding: 'FieldBinder[DeliminatedFloat, float]',
        wavelength: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._binding = binding

        self._title = QLabel('Power Setpoint')
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(10)
        self._spin = QDoubleSpinBox()
        self._spin.setDecimals(2)
        self._spin.setSuffix(' mW')
        self._spin.setSingleStep(0.1)
        self._spin.setKeyboardTracking(False)

        lay = QVBoxLayout(self)
        lay.addWidget(self._title)
        lay.addWidget(self._slider)
        lay.addWidget(self._spin)

        # Device → UI (single renderer)
        self._binding.value_changed.connect(self._render_df)

        # UI → Device
        self._slider.setTracking(True)
        self._slider.valueChanged.connect(lambda i: self._binding.set_value(float(i)))
        self._spin.valueChanged.connect(lambda: self._binding.set_value(self._spin.value()))

        # Initial paint (if available)
        if (df := self._binding.get_value()) is not None:
            self._render_df(df)

        if wavelength is not None:
            self._apply_wavelength_style(wavelength)

    def _render_df(self, df: 'DeliminatedFloat') -> None:
        min_v = float(df.min_value or 0.0)
        max_v = float(df.max_value or 100.0)
        step = float(df.step or 1.0)
        fval = float(df)

        with QSignalBlocker(self._slider), QSignalBlocker(self._spin):
            self._slider.setMinimum(int(min_v))
            self._slider.setMaximum(int(max_v))
            self._slider.setSingleStep(int(step))
            self._slider.setTickInterval((int(max_v - min_v) // 10) or 10)
            self._slider.setValue(int(fval))

            self._spin.setMinimum(min_v)
            self._spin.setMaximum(max_v)
            self._spin.setSingleStep(step)
            self._spin.setValue(fval)

    def _apply_wavelength_style(self, wavelength: int) -> None:
        palette = self._slider.palette()
        r, g, b = wavelength_to_rgb(wavelength)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 12px;
                background: {palette.color(palette.ColorRole.Base).name()};
                border-radius: 6px;
            }}
            QSlider::handle:horizontal {{
                background: {rgb_to_css_string((r, g, b))};
                border: 1px solid {rgb_to_css_string((r // 2, g // 2, b // 2))};
                width: 18px;
                margin: -4px 0;
                border-radius: 9px;
            }}
            QSlider::sub-page:horizontal {{
                background: {rgb_to_css_string((r * 0.8, g * 0.8, b * 0.8))};
                border-radius: 6px;
            }}
            QSlider::add-page:horizontal {{
                background: {palette.color(palette.ColorRole.AlternateBase).name()};
                border-radius: 6px;
            }}
        """)

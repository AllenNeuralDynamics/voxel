from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget
from vidgets.devices.laser.utils import rgb_to_css_string, wavelength_to_rgb
from vidgets.input.binding import ValueBinding
from voxel.devices.laser import VoxelLaser
from voxel.utils.descriptors.deliminated import DeliminatedFloat


class DeliminatedFloatInput(QWidget):
    def __init__(self, getter: Callable[[], DeliminatedFloat], setter: Callable[[float], None], unit: str) -> None:
        """Widget for editing a DeliminatedFloat with both a slider (coarse) and spinbox (precise).

        Args:
        getter: Callable returning the current DeliminatedFloat
        setter: Callable accepting a float value
        unit: For displaying units (e.g. "mW", "V", etc.)
        """
        super().__init__()

        self._binding = ValueBinding[DeliminatedFloat, float](
            getter=getter,
            setter=setter,
            watch_interval=500,
            parent=self,
        )

        # Widgets
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(10)

        self._spinbox = QDoubleSpinBox()
        self._spinbox.setDecimals(2)
        self._spinbox.setSuffix(f' {unit}')
        self._spinbox.setSingleStep(0.1)

        self._min_label = QLabel('Min:')
        self._max_label = QLabel('Max:')
        self._step_label = QLabel('Step:')
        self._setp_label = QLabel('Setpoint:')

        # Layout
        labels = QHBoxLayout()
        labels.addWidget(self._min_label)
        labels.addWidget(self._max_label)
        labels.addWidget(self._step_label)
        labels.addWidget(self._setp_label)

        layout = QVBoxLayout()
        layout.addLayout(labels)
        layout.addWidget(self._slider)
        layout.addWidget(self._spinbox)
        self.setLayout(layout)

        # Render function (updates slider, spinbox, labels)
        def _render(val: DeliminatedFloat) -> None:
            min_val = val.min_value or 0.0
            max_val = val.max_value or 100.0
            step = val.step or 1.0
            fval = float(val)

            # Labels
            self._min_label.setText(f'Min: {min_val}')
            self._max_label.setText(f'Max: {max_val}')
            self._step_label.setText(f'Step: {step}')
            self._setp_label.setText(f'Setpoint: {fval:.2f}')

            # Spinbox
            with QSignalBlocker(self._spinbox):
                self._spinbox.setMinimum(min_val)
                self._spinbox.setMaximum(max_val)
                self._spinbox.setSingleStep(step)
                self._spinbox.setValue(fval)

            # Slider
            with QSignalBlocker(self._slider):
                self._slider.setMinimum(int(min_val))
                self._slider.setMaximum(int(max_val))
                self._slider.setSingleStep(int(step))
                self._slider.setValue(int(fval))
                self._slider.setTickInterval((int(max_val - min_val) // 10) or 10)

        # Initial render
        _render(self._binding.get_value())

        # Device → UI
        self._binding.value_changed.connect(_render)

        # UI → Device
        # Slider: only emit when the handle is released
        self._slider.valueChanged.connect(lambda i: self._binding.set_value(i))
        self._slider.setTracking(True)

        # Spinbox: only emit when user finishes editing (Enter / focus-out)
        self._spinbox.editingFinished.connect(lambda: self._binding.set_value(self._spinbox.value()))
        # self._spinbox.setKeyboardTracking(False)
        # self._spinbox.valueChanged.connect(self._binding.set_value) # better to only update on editingFinished


class PowerSetpointInput(DeliminatedFloatInput):
    def __init__(
        self, getter: Callable[[], DeliminatedFloat], setter: Callable[[float], None], wavelength: int
    ) -> None:
        super().__init__(getter=getter, setter=setter, unit='mW')
        self._wavelength = wavelength
        self._apply_wavelength_style(wavelength)

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


class LaserWidget(QWidget):
    def __init__(self, laser: VoxelLaser) -> None:
        super().__init__()
        self._laser = laser

        def _set_power_setpoint(value: float) -> None:
            self._laser.power_setpoint_mw = value

        self._slider = PowerSetpointInput(
            getter=lambda: self._laser.power_setpoint_mw,
            setter=_set_power_setpoint,
            wavelength=self._laser.wavelength,
        )

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f'Laser - Wavelength: {self._laser.wavelength} nm'))
        layout.addWidget(self._slider)
        self.setLayout(layout)


if __name__ == '__main__':
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
    )
    from voxel.devices.laser.mock import SimulatedLaser
    from voxel.utils.log import VoxelLogging

    class LaserWidgetDemo(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle('Laser Widget Demo')
            self.setGeometry(100, 100, 500, 200)

            laser = SimulatedLaser(wavelength=488)
            laser.power_setpoint_mw = 50.0

            self.setCentralWidget(LaserWidget(laser=laser))

    VoxelLogging.setup(level='DEBUG')

    app = QApplication([])
    demo = LaserWidgetDemo()
    demo.show()
    app.exec()

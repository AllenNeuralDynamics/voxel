from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QSizePolicy
from exaspim_control.voxel_classic.devices.laser.base import BaseLaser
from exaspim_control.view.base_device_widget import BaseDeviceWidget, create_widget
from exaspim_control.view.miscellaneous_widgets.q_scrollable_float_slider import QScrollableFloatSlider


class LaserWidget(BaseDeviceWidget):
    """Widget for handling laser properties and controls."""

    def __init__(self, laser: BaseLaser):
        """
        Initialize the LaserWidget object.

        :param laser: Laser object
        :type laser: BaseLaser
        """
        self._laser = laser
        super().__init__(
            device_type=type(self._laser),
            properties={
                'power_setpoint_mw': self._laser.power_setpoint_mw,
                'power_mw': self._laser.power_mw,
                'temperature_c': self._laser.temperature_c,
            },
            updating_props=['power_setpoint_mw', 'power_mw', 'temperature_c'],
        )
        self.attach_device(self._laser)

        self.slider_color = self._laser.color if self._laser.color != 'unknown' else 'white'
        self.max_power_mw = getattr(type(self._laser).power_setpoint_mw, 'maximum', 110)
        self.add_power_slider()

    def add_power_slider(self) -> None:
        """
        Add a power slider to the widget.
        """
        setpoint = self.power_setpoint_mw_widget  # type: ignore
        power = self.power_mw_widget  # type: ignore
        temperature = self.property_widgets['temperature_c'].layout().itemAt(1).widget()

        if isinstance(setpoint.validator(), QDoubleValidator):
            setpoint.validator().setRange(0.0, self.max_power_mw, 2)  # decimals is positional, not keyword
            power.validator().setRange(0.0, self.max_power_mw, 2)
        elif isinstance(setpoint.validator(), QIntValidator):
            setpoint.validator().setRange(0, int(self.max_power_mw))
            power.validator().setRange(0, int(self.max_power_mw))

        power.setEnabled(False)
        power.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        power.setMinimumWidth(60)
        power.setMaximumWidth(60)

        setpoint.validator().fixup = self.power_slider_fixup
        setpoint.editingFinished.connect(lambda: slider.setValue(round(float(setpoint.text()))))
        setpoint.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        setpoint.setMinimumWidth(60)
        setpoint.setMaximumWidth(60)

        power_mw_label = self.property_widgets['power_mw'].layout().itemAt(0).widget()
        power_mw_label.setVisible(False)  # hide power_mw label

        slider = QScrollableFloatSlider(orientation=Qt.Orientation.Horizontal)
        slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # active slider color
        hsv_color = QColor(self.slider_color)
        h, s, v, a = hsv_color.hue(), hsv_color.saturation(), hsv_color.value(), hsv_color.alpha()
        hsv_active_color = [h if h >= 0 else 0, s, v, a]
        active_color = QColor.fromHsv(*hsv_active_color).name()

        # inactive slide color
        hsv_inactive_color = hsv_active_color.copy()
        hsv_inactive_color[2] = hsv_inactive_color[2] // 4
        inactive_color = QColor.fromHsv(*hsv_inactive_color).name()

        # border color
        hsv_border_color = hsv_active_color.copy()
        hsv_border_color[2] = 100
        hsv_border_color[1] = 100
        border_color = QColor.fromHsv(*hsv_border_color).name()

        # handle color
        hsv_handle_color = hsv_active_color.copy()
        hsv_handle_color[2] = 128
        hsv_handle_color[1] = 64
        handle_color = QColor.fromHsv(*hsv_handle_color).name()

        slider.setStyleSheet(
            f'QSlider::groove:horizontal {{background: {inactive_color}; border: 2px solid {border_color};height: 10px;border-radius: 6px;}}'
            f'QSlider::handle:horizontal {{background-color: {handle_color}; width: 16px; height: 14px; '
            f'line-height: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 0px; }}'
            f'QSlider::sub-page:horizontal {{background: {active_color};border: 2px solid {border_color};'
            f'height: 10px;border-radius: 6px;}}'
        )

        slider.setMinimum(0)  # Todo: is it always zero?
        slider.setMaximum(int(self.max_power_mw))
        slider.setValue(int(self.power_setpoint_mw))  # type: ignore
        slider.sliderMoved.connect(lambda: setpoint.setText(str(slider.value())))
        slider.sliderReleased.connect(lambda: setattr(self, 'power_setpoint_mw', float(slider.value())))
        slider.sliderReleased.connect(lambda: self.ValueChangedInside.emit('power_setpoint_mw'))

        temperature.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        temperature.setMinimumWidth(50)
        temperature.setMaximumWidth(50)

        self.power_setpoint_mw_widget_slider = slider
        self.property_widgets['power_setpoint_mw'].layout().addWidget(
            create_widget(
                'H', setpoint, self.property_widgets['power_mw'], slider, self.property_widgets['temperature_c']
            )
        )

    def power_slider_fixup(self, value: str) -> None:
        """
        Fix the power slider value.

        :param value: Value to fix
        :type value: str
        """
        self.power_setpoint_mw_widget.setText(str(self.max_power_mw))  # type: ignore
        self.power_setpoint_mw_widget.editingFinished.emit()  # type: ignore

import importlib

from qtpy.QtCore import Qt
from qtpy.QtGui import QDoubleValidator, QIntValidator, QColor
from qtpy.QtWidgets import QSizePolicy

from view.widgets.base_device_widget import BaseDeviceWidget, create_widget, scan_for_properties
from view.widgets.miscellaneous_widgets.q_scrollable_float_slider import QScrollableFloatSlider


class LaserWidget(BaseDeviceWidget):
    """Widget for handling laser properties and controls."""

    def __init__(self, laser: object, color: str = "blue", advanced_user: bool = True):
        """
        Initialize the LaserWidget object.

        :param laser: Laser object
        :type laser: object
        :param color: Color of the slider, defaults to "blue"
        :type color: str, optional
        :param advanced_user: Whether the user is advanced, defaults to True
        :type advanced_user: bool, optional
        """
        self.laser_properties = (
            scan_for_properties(laser)
            if advanced_user
            else {
                "power_setpoint_mw": laser.power_setpoint_mw,
                "power_mw": laser.power_mw,
                "temperature_c": laser.temperature_c,
            }
        )
        self.laser_module = importlib.import_module(laser.__module__)
        self.slider_color = color
        super().__init__(type(laser), self.laser_properties)
        self.max_power_mw = getattr(type(laser).power_setpoint_mw, "maximum", 110)
        self.add_power_slider()

    def add_power_slider(self) -> None:
        """
        Add a power slider to the widget.
        """
        setpoint = self.power_setpoint_mw_widget
        power = self.power_mw_widget
        temperature = self.property_widgets["temperature_c"].layout().itemAt(1).widget()

        if type(setpoint.validator()) == QDoubleValidator:
            setpoint.validator().setRange(0.0, self.max_power_mw, decimals=2)
            power.validator().setRange(0.0, self.max_power_mw, decimals=2)
        elif type(setpoint.validator()) == QIntValidator:
            setpoint.validator().setRange(0, self.max_power_mw)
            power.validator().setRange(0.0, self.max_power_mw)

        power.setEnabled(False)
        power.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        power.setMinimumWidth(60)
        power.setMaximumWidth(60)

        setpoint.validator().fixup = self.power_slider_fixup
        setpoint.editingFinished.connect(lambda: slider.setValue(round(float(setpoint.text()))))
        setpoint.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        setpoint.setMinimumWidth(60)
        setpoint.setMaximumWidth(60)

        power_mw_label = self.property_widgets["power_mw"].layout().itemAt(0).widget()
        power_mw_label.setVisible(False)  # hide power_mw label

        slider = QScrollableFloatSlider(orientation=Qt.Horizontal)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # active slider color
        hsv_active_color = list(QColor(self.slider_color).getHsv())
        active_color = QColor.fromHsv(*tuple(hsv_active_color)).name()

        # inactive slide color
        hsv_inactive_color = hsv_active_color
        hsv_inactive_color[2] = hsv_inactive_color[2] // 4
        inactive_color = QColor.fromHsv(*tuple(hsv_inactive_color)).name()

        # border color
        hsv_border_color = hsv_active_color
        hsv_border_color[2] = 100
        hsv_border_color[1] = 100
        border_color = QColor.fromHsv(*tuple(hsv_border_color)).name()

        # handle color
        hsv_handle_color = hsv_active_color
        hsv_handle_color[2] = 128
        hsv_handle_color[1] = 64
        handle_color = QColor.fromHsv(*tuple(hsv_handle_color)).name()

        slider.setStyleSheet(
            f"QSlider::groove:horizontal {{background: {inactive_color}; border: 2px solid {border_color};height: 10px;border-radius: 6px;}}"
            f"QSlider::handle:horizontal {{background-color: {handle_color}; width: 16px; height: 14px; "
            f"line-height: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 0px; }}"
            f"QSlider::sub-page:horizontal {{background: {active_color};border: 2px solid {border_color};"
            f"height: 10px;border-radius: 6px;}}"
        )

        slider.setMinimum(0)  # Todo: is it always zero?
        slider.setMaximum(int(self.max_power_mw))
        slider.setValue(int(self.power_setpoint_mw))
        slider.sliderMoved.connect(lambda: setpoint.setText(str(slider.value())))
        slider.sliderReleased.connect(lambda: setattr(self, "power_setpoint_mw", float(slider.value())))
        slider.sliderReleased.connect(lambda: self.ValueChangedInside.emit("power_setpoint_mw"))

        temperature.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        temperature.setMinimumWidth(50)
        temperature.setMaximumWidth(50)

        self.power_setpoint_mw_widget_slider = slider
        self.property_widgets["power_setpoint_mw"].layout().addWidget(
            create_widget(
                "H", setpoint, self.property_widgets["power_mw"], slider, self.property_widgets["temperature_c"]
            )
        )

    def power_slider_fixup(self, value: str) -> None:
        """
        Fix the power slider value.

        :param value: Value to fix
        :type value: str
        """
        self.power_setpoint_mw_widget.setText(str(self.max_power_mw))
        self.power_setpoint_mw_widget.editingFinished.emit()

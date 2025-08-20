import contextlib
from collections.abc import Callable
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QStyle, QVBoxLayout, QWidget

from vidgets.view.base_device_widget import BaseDeviceWidget, create_widget, disable_button, scan_for_properties
from voxel_classic.devices.camera.base import BaseCamera


class CameraWidget(BaseDeviceWidget):
    """Widget for handling camera properties and controls."""

    def __init__(self, camera: BaseCamera, advanced_user: bool = True):
        """
        Initialize the CameraWidget object.

        :param camera: Camera object
        :type camera: object
        :param advanced_user: Whether the user is advanced, defaults to True
        :type advanced_user: bool, optional
        """
        self.camera_properties = scan_for_properties(camera)
        del self.camera_properties["latest_frame"]  # remove image property

        super().__init__(type(camera), properties=self.camera_properties, updating_props=None)
        self.attach_device(camera)

        # hide all property widgets by default
        for widget in self.property_widgets.values():
            widget.setVisible(False)
        # show only select widgets
        self.property_widgets["pixel_type"].setVisible(True)

        # create and format livestream button and snapshot button
        self.live_button = self.create_live_button()
        self.snapshot_button = self.create_snapshot_button()
        self.alignment_button = self.create_alignment_button()
        self.crosshairs_button = self.create_crosshairs_button()
        combobox_pixel_type = self.property_widgets["pixel_type"].layout().itemAt(1).widget()
        combobox_pixel_type_label = self.property_widgets["pixel_type"].layout().itemAt(0).widget()
        combobox_pixel_type_label.setVisible(False)  # hide power_mw label
        picture_buttons = create_widget(
            "H",
            self.live_button,
            self.snapshot_button,
            self.alignment_button,
            self.crosshairs_button,
            combobox_pixel_type,
        )

        if advanced_user:  # format widgets better in advanced user mode
            # show only select widgets
            self.property_widgets["pixel_type"].setVisible(True)
            self.property_widgets["exposure_time_ms"].setVisible(True)
            self.property_widgets["frame_time_ms"].setVisible(True)
            self.property_widgets["line_interval_us"].setVisible(True)
            self.property_widgets["width_px"].setVisible(True)
            self.property_widgets["height_px"].setVisible(True)
            self.property_widgets["width_offset_px"].setVisible(True)
            self.property_widgets["height_offset_px"].setVisible(True)
            self.property_widgets["image_width_px"].setVisible(True)
            self.property_widgets["image_height_px"].setVisible(True)
            self.property_widgets["height_offset_px"].setVisible(True)
            self.property_widgets["sensor_width_px"].setVisible(True)
            self.property_widgets["sensor_height_px"].setVisible(True)
            self.property_widgets["binning"].setVisible(True)
            self.property_widgets["readout_mode"].setVisible(True)
            self.property_widgets["trigger"].setVisible(True)
            self.property_widgets["sensor_temperature_c"].setVisible(True)
            self.property_widgets["mainboard_temperature_c"].setVisible(True)

            _ = QWidget()  # dummy widget
            direct = Qt.FindChildOption.FindDirectChildrenOnly

            # reformat timing widgets
            timing_widgets = create_widget(
                "VH",
                *self.property_widgets.get("exposure_time_ms", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("frame_time_ms", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("line_interval_us", _).findChildren(QWidget, options=direct),
            )
            # check if properties have setters and if not, disable widgets
            for i, prop in enumerate(["exposure_time_ms", "frame_time_ms", "line_interval_us"]):
                attr = getattr(type(camera), prop, False)
                children = timing_widgets.children()
                if len(children) > i + 1:
                    child = children[i + 1]
                    if hasattr(child, "setEnabled"):
                        if getattr(attr, "fset", None) is None:
                            child.setEnabled(False)  # type: ignore
                        if prop == "line_interval_us":
                            child.setEnabled(False)  # type: ignore

            # reformat sensor width widget
            width_widget = create_widget(
                "HV",
                *self.property_widgets.get("width_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("width_offset_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("image_width_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("sensor_width_px", _).findChildren(QWidget, options=direct),
            )

            # check if properties have setters and if not, disable widgets
            for i, prop in enumerate(["width_px", "width_offset_px", "sensor_width_px", "image_width_px"]):
                attr = getattr(type(camera), prop, False)
                children = width_widget.children()
                if len(children) > i + 1:
                    child = children[i + 1]
                    if hasattr(child, "setEnabled") and getattr(attr, "fset", None) is None:
                        child.setEnabled(False)  # type: ignore

            # reformat sensor height widget
            height_widget = create_widget(
                "HV",
                *self.property_widgets.get("height_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("height_offset_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("image_height_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("sensor_height_px", _).findChildren(QWidget, options=direct),
            )

            # check if properties have setters and if not, disable widgets
            for i, prop in enumerate(["height_px", "height_offset_px", "sensor_height_px", "image_height_px"]):
                attr = getattr(type(camera), prop, False)
                children = height_widget.children()
                if len(children) > i + 1:
                    child = children[i + 1]
                    if hasattr(child, "setEnabled") and getattr(attr, "fset", None) is None:
                        child.setEnabled(False)  # type: ignore

            # combine timing, width, and height widgets
            roi_widget = create_widget("H", width_widget, height_widget)
            combined_widget = create_widget("V", timing_widgets, roi_widget)
            layout = QVBoxLayout()
            layout.addWidget(combined_widget)

            # reformat pixel options widgets
            pixel_widgets = create_widget(
                "HV",
                *self.property_widgets.get("binning", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("sampling_um_px", _).findChildren(QWidget, options=direct),
                *self.property_widgets.get("readout_mode", _).findChildren(QWidget, options=direct),
            )

            # check if properties have setters and if not, disable widgets. Have to do it inside pixel widget
            for i, prop in enumerate(["binning", "sampling_um_px", "readout_mode"]):
                attr = getattr(type(camera), prop)
                children = pixel_widgets.children()
                if len(children) > i + 1:
                    child = children[i + 1]
                    if hasattr(child, "setEnabled") and getattr(attr, "fset", None) is None:
                        child.setEnabled(False)  # type: ignore

            # reformat trigger widget
            trigger_widget_label = self.property_widgets["trigger"].layout().itemAt(0).widget()
            trigger_widget_label.setVisible(False)  # hide power_mw label
            trigger_widget = self.property_widgets["trigger"].layout().itemAt(1).widget()
            trigger_mode_widget = trigger_widget.layout().itemAt(0)
            trigger_mode_widget.widget().layout().itemAt(0).widget().setText("Trigger Mode")
            trigger_source_widget = trigger_widget.layout().itemAt(1)
            trigger_source_widget.widget().layout().itemAt(0).widget().setText("Trigger Source")
            trigger_polarity_widget = trigger_widget.layout().itemAt(2)
            trigger_polarity_widget.widget().layout().itemAt(0).widget().setText("Trigger Polarity")

            trigger_widget = create_widget(
                "V", trigger_mode_widget.widget(), trigger_source_widget.widget(), trigger_polarity_widget.widget()
            )

            # reformat pixel trigger widget
            pixel_trigger_widget = create_widget("H", pixel_widgets, trigger_widget)

            # reformat temperature widgets
            sensor_temperature_c = self.property_widgets["sensor_temperature_c"].layout().itemAt(1).widget()
            sensor_temperature_c.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
            sensor_temperature_c.setMinimumWidth(40)
            sensor_temperature_c.setMaximumWidth(40)

            textbox_mainboard_temperature_c = (
                self.property_widgets["mainboard_temperature_c"].layout().itemAt(1).widget()
            )
            textbox_mainboard_temperature_c.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
            textbox_mainboard_temperature_c.setMinimumWidth(40)
            textbox_mainboard_temperature_c.setMaximumWidth(40)

            temperature_widget = create_widget(
                "H", self.property_widgets["sensor_temperature_c"], self.property_widgets["mainboard_temperature_c"]
            )

            central_widget = self.centralWidget()
            if central_widget is not None and central_widget.layout() is not None:
                central_widget.layout().setSpacing(0)  # type: ignore  # remove space between central widget and newly formatted widgets
            self.setCentralWidget(
                create_widget(
                    "V", picture_buttons, combined_widget, pixel_trigger_widget, temperature_widget, central_widget
                )
            )
        else:  # add snapshot button and liveview
            central_widget = self.centralWidget()
            if central_widget is not None and central_widget.layout() is not None:
                central_widget.layout().setSpacing(0)  # type: ignore  # remove space between central widget and newly formatted widgets
            self.setCentralWidget(create_widget("H", self.live_button, self.snapshot_button))

        # check if frame_time_ms_widget exits and its has a validator
        if hasattr(self, "frame_time_ms_widget") and hasattr(self.frame_time_ms_widget, "validator"):  # type: ignore
            validator = self.frame_time_ms_widget.validator()  # type: ignore
            if validator is not None and hasattr(validator, "setDecimals"):
                validator.setDecimals(2)  # type: ignore  # set frame time decimals to 2
        if hasattr(self, "exposure_time_ms_widget") and hasattr(self.exposure_time_ms_widget, "validator"):  # type: ignore
            validator = self.exposure_time_ms_widget.validator()  # type: ignore
            if validator is not None and hasattr(validator, "setDecimals"):
                validator.setDecimals(2)  # type: ignore  # set exposure time decimals to 2

    def disable_action_buttons(self):
        for btn in [self.live_button, self.snapshot_button, self.alignment_button, self.crosshairs_button]:
            btn.setEnabled(False)
            btn.setDisabled(True)
            btn.repaint()

    def enable_action_buttons(self):
        for btn in [self.live_button, self.snapshot_button, self.alignment_button, self.crosshairs_button]:
            btn.setEnabled(True)
            btn.setDisabled(False)
            btn.repaint()

    def configure_live_button_to_start(self, callback: Callable[[], None]):
        with contextlib.suppress(TypeError, RuntimeError):
            self.live_button.pressed.disconnect()  # Disconnect all pressed signals
        self.live_button.setText("Live")
        style = self.live_button.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            self.live_button.setIcon(icon)
        self.live_button.pressed.connect(lambda: disable_button(self.live_button))
        self.live_button.pressed.connect(callback)

    def configure_live_button_to_stop(self, callback: Callable[[], None]):
        with contextlib.suppress(TypeError, RuntimeError):
            self.live_button.pressed.disconnect()  # Disconnect all pressed signals
        self.live_button.setText("Stop")
        style = self.live_button.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
            self.live_button.setIcon(icon)
        self.live_button.pressed.connect(lambda: disable_button(self.live_button))
        self.live_button.pressed.connect(callback)

    def create_live_button(self):
        """
        Create the live button.

        :return: Live button
        :rtype: QPushButton
        """
        button = QPushButton("Live")
        style = self.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
            button.setIcon(icon)

        return button

    def create_snapshot_button(self):
        """
        Create the snapshot button.

        :return: Snapshot button
        :rtype: QPushButton
        """
        button = QPushButton("Snapshot")
        style = self.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
            button.setIcon(icon)
        button.pressed.connect(lambda: disable_button(button))
        return button

    def create_alignment_button(self):
        """
        Create the alignment button.

        :return: Alignment button
        :rtype: QPushButton
        """
        button = QPushButton("Alignment")
        style = self.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton)
            button.setIcon(icon)
        button.setCheckable(True)
        return button

    def create_crosshairs_button(self):
        """
        Create the crosshairs button.

        :return: Crosshairs button
        :rtype: QPushButton
        """
        button = QPushButton("Crosshair")
        style = self.style()
        if style is not None:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_DockWidgetCloseButton)
            button.setIcon(icon)
        button.setCheckable(True)
        return button

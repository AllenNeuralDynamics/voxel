import contextlib
import importlib
import inspect
import logging
import time
from collections.abc import Generator, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import inflection
import napari
import numpy as np
import tifffile
from napari.layers import Image
from napari.qt.threading import WorkerBase, create_worker, thread_worker
from napari.utils.events import Event
from napari.utils.theme import get_theme
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtCore import pyqtSlot as Slot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml import YAML, RoundTripRepresenter
from view.acquisition_view import AcquisitionView
from view.widgets.acquisition_widgets.channel_plan_widget import ChannelPlanWidget
from view.widgets.acquisition_widgets.volume_model import VolumeModel
from view.widgets.acquisition_widgets.volume_plan_widget import VolumePlanWidget
from view.widgets.base_device_widget import BaseDeviceWidget, create_widget, disable_button, scan_for_properties
from view.widgets.device_widgets.camera_widget import CameraWidget
from view.widgets.device_widgets.filter_wheel_widget import FilterWheelWidget
from view.widgets.device_widgets.flip_mount_widget import FlipMountWidget
from view.widgets.device_widgets.laser_widget import LaserWidget
from view.widgets.device_widgets.ni_widget import NIWidget
from view.widgets.device_widgets.stage_widget import StageWidget
from voxel.utils.log import VoxelLogging
from voxel_classic.devices.base import VoxelDevice
from voxel_classic.processes.downsample.gpu.gputools.rank_downsample_2d import GPUToolsRankDownSample2D

from exaspim_control.exa_spim_instrument import ExASPIM


class NonAliasingRTRepresenter(RoundTripRepresenter):
    """
    Custom representer for ruamel.yaml to ignore aliases.
    This class is used to ensure that YAML files do not contain aliases,
    which can cause issues with certain YAML parsers.
    It overrides the `ignore_aliases` method to always return True.
    This prevents ruamel.yaml from creating aliases for any data structures
    that it represents.

    :param ruamel: ruamel.yaml.RoundTripRepresenter
    :type ruamel: ruamel.yaml.RoundTripRepresenter
    """

    def ignore_aliases(self, data):
        return True


class ExASPIMInstrumentView(QWidget):
    """Class for handling ExASPIM instrument view."""

    snapshotTaken = Signal((np.ndarray, list))
    contrastChanged = Signal((np.ndarray, list))

    def __init__(self, instrument: ExASPIM, config: dict[str, Any]) -> None:
        """
        Initialize the ExASPIMInstrumentView object.

        :param instrument: Instrument object
        :type instrument: Instrument
        :param config: Configuration dictionary. loaded from gui_config.yaml
        :type config: dict[str, Any]
        """
        super().__init__()

        self.log = VoxelLogging.get_logger(object=self)
        log_level = logging.getLevelName(self.log.getEffectiveLevel())

        # TODO: Manage elsewhere
        # set all loggers to log_level
        loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
        for logger in loggers:
            logger.setLevel(log_level)

        self.instrument: ExASPIM = instrument
        self.config: dict[str, Any] = config

        # Setup napari window
        self.viewer = napari.Viewer(title="ExA-SPIM control", ndisplay=2, axis_labels=("x", "y"))

        # Add widget groups ---------------------------------------------------

        # Left
        self.stages_widget: QScrollArea = self._create_stage_widgets_scroll_area()
        self.viewer.window.add_dock_widget(self.stages_widget, area="left", name="Stages")

        # Right
        self.camera_widgets: dict[str, CameraWidget] = self._create_camera_widgets()
        self.viewer.window.add_dock_widget(
            self._stack_device_widgets(device_widgets=self.camera_widgets),
            area="right",
            name="Cameras",
            add_vertical_stretch=False,
        )

        self.daq_widgets: dict[str, NIWidget] = self._create_daq_widgets()
        self.viewer.window.add_dock_widget(
            self._stack_device_widgets(device_widgets=self.daq_widgets),
            area="right",
            name="DAQ",
            add_vertical_stretch=False,
        )

        self.filter_wheel_widgets: dict[str, FilterWheelWidget] = self._create_filter_wheel_widgets()
        self.viewer.window.add_dock_widget(
            self._stack_device_widgets(device_widgets=self.filter_wheel_widgets),
            area="right",
            name="Filter Wheels",
            add_vertical_stretch=False,
        )

        self.flip_mount_widgets: dict[str, FlipMountWidget] = {}

        # Bottom
        self.compound_laser_widget, self.laser_widgets = self._create_laser_widgets()
        self.viewer.window.add_dock_widget(self.compound_laser_widget, area="bottom", name="Lasers")

        self.channels_widget, self.laser_combo_box = self._create_channels_widget()
        self.livestream_channel = self.laser_combo_box.currentText()  # initialize livestream channel

        self.property_workers: dict[str, WorkerBase] = {}
        self.grab_frames_worker: WorkerBase = create_worker(lambda: None)

        for device_name, device_specs in self.instrument.config["instrument"]["devices"].items():
            device_type = device_specs["type"]
            if device_type not in ["camera", "laser", "daq", "flip_mount", "stage", "filter_wheel"]:
                self._create_device_widgets(device_name, device_specs)

        # add undocked widget so everything closes together
        self._add_undocked_widgets()

        # Set app events
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.aboutToQuit.connect(self._update_config_on_quit)
            self.config_save_to = self.instrument.config_path
            app.lastWindowClosed.connect(self.close)

        # Configure Viewer
        self.intensity_min = self.config["instrument_view"]["properties"]["intensity_min"]
        if self.intensity_min < 0 or self.intensity_min > 65535:
            raise ValueError("intensity min must be between 0 and 65535")
        self.intensity_max = self.config["instrument_view"]["properties"]["intensity_max"]
        if self.intensity_max < self.intensity_min or self.intensity_max > 65535:
            raise ValueError("intensity max must be between intensity min and 65535")
        self.camera_rotation = self.config["instrument_view"]["properties"]["camera_rotation_deg"]
        if self.camera_rotation not in [0, 90, 180, 270, 360, -90, -180, -270]:
            raise ValueError("camera rotation must be 0, 90, 180, 270, -90, -180, -270")
        self.resolution_levels = self.config["instrument_view"]["properties"]["resolution_levels"]
        if self.resolution_levels < 1 or self.resolution_levels > 10:
            raise ValueError("resolution levels must be between 1 and 10")
        self.alignment_roi_size = self.config["instrument_view"]["properties"]["alignment_roi_size"]
        if self.alignment_roi_size < 2 or self.alignment_roi_size > 1024:
            raise ValueError("alignment roi size must be between 2 and 1024")
        self.viewer.scale_bar.visible = True
        self.viewer.scale_bar.unit = "um"
        self.viewer.scale_bar.position = "bottom_left"
        self.viewer.text_overlay.visible = True

        def _update_fps(self, fps: float) -> None:
            self.viewer.text_overlay.text = f"{fps:1.1f} fps"

        self.viewer.window._qt_viewer.canvas._scene_canvas.measure_fps(callback=_update_fps)

        self.downsampler = GPUToolsRankDownSample2D(binning=2, rank=-2, data_type="uint16")

        # setup and connect viewer camera events
        # Reset camera to default state
        self.viewer.camera.zoom = 1.0
        self.viewer.camera.center = (0, 0)
        self.viewer.camera.angles = (0, 0, 0)
        self.viewer_state = {
            "zoom": self.viewer.camera.zoom,
            "center": self.viewer.camera.center,
            "angles": self.viewer.camera.angles,
        }
        self.previous_layer = None

        def _camera_zoom(self, event: Event) -> None:
            """Store viewer state anytime camera zooms and there is a layer."""
            if self.previous_layer and self.previous_layer in self.viewer.layers:
                self.viewer_state = {
                    "zoom": self.viewer.camera.zoom,
                    "center": self.viewer.camera.center,
                    "angles": self.viewer.camera.angles,
                }

        def _camera_position(self, event: Event) -> None:
            """Store viewer state anytime camera moves and there is a layer."""
            if self.previous_layer and self.previous_layer in self.viewer.layers:
                self.viewer_state = {
                    "zoom": self.viewer.camera.zoom,
                    "center": self.viewer.camera.center,
                    "angles": self.viewer.camera.angles,
                }

        self.viewer.camera.events.zoom.connect(_camera_zoom)
        self.viewer.camera.events.center.connect(_camera_position)

        # create cache for contrast limit values
        self.contrast_limits = {}
        for key in self.instrument.channels:
            self.contrast_limits[key] = [self.intensity_min, self.intensity_max]

    def _create_laser_widgets(self) -> tuple[QWidget, dict[str, LaserWidget]]:
        laser_widgets = {}
        hframes: list[QFrame] = []
        devices_specs = self.instrument.config["instrument"]["devices"]
        for laser_name, laser in self.instrument.lasers.items():
            laser_color = (devices_specs or {}).get(laser_name, {}).get("color", "blue")
            laser_widget = LaserWidget(laser=laser, color=laser_color, advanced_user=True)
            laser_widgets[laser_name] = laser_widget

            label = QLabel(laser_name)
            hframe = QFrame()
            layout = QVBoxLayout()
            layout.addWidget(create_widget("H", label, laser_widget))
            hframe.setLayout(layout)
            border_color = get_theme(self.viewer.theme, as_dict=False).foreground
            hframe.setStyleSheet(f".QFrame {{ border:1px solid {border_color}; }} ")

            hframes.append(hframe)

        compound_widget = create_widget("V", *hframes)

        return compound_widget, laser_widgets

    def _create_stage_widgets_scroll_area(self) -> QScrollArea:
        stage_widgets = []
        instrument_stages = {
            **self.instrument.focusing_stages,
            **self.instrument.tiling_stages,
            **self.instrument.scanning_stages,
        }
        for stage_name, stage in instrument_stages.items():
            label = QLabel()
            layout = QVBoxLayout()
            layout.addWidget(create_widget("H", label, StageWidget(stage=stage, advanced_user=True)))
            stage_widgets.append(layout)

        stage_axes_widget = create_widget("V", *stage_widgets)
        if stage_axes_widget is not None:
            stage_axes_widget.setContentsMargins(0, 0, 0, 0)
            layout = stage_axes_widget.layout()
            if layout is not None:
                layout.setSpacing(6)

        stage_scroll = QScrollArea()
        stage_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stage_scroll.setWidget(stage_axes_widget)

        return stage_scroll

    def _create_camera_widgets(self) -> dict[str, CameraWidget]:
        camera_widgets = {}
        for camera_name, camera in self.instrument.cameras.items():
            wgt = CameraWidget(camera=camera, advanced_user=True)
            camera_widgets[camera_name] = wgt

            # Add functionality to snapshot button
            self.snapshot_button = wgt.snapshot_button
            wgt.snapshot_button.pressed.connect(lambda button=wgt.snapshot_button: disable_button(button))
            wgt.snapshot_button.pressed.connect(lambda camera=camera_name: self._setup_live(camera, 1))

            # Add functionality to live button
            def _configure_live_button():
                btn = wgt.live_button
                if self.grab_frames_worker.is_running:
                    if btn.text != "Stop":
                        btn.setText("Stop")
                        style = btn.style()
                        if style is not None:
                            stop_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
                            btn.setIcon(stop_icon)
                    btn.disconnect()
                    btn.pressed.connect(self.grab_frames_worker.quit)
                else:
                    if btn.text() != "Live":
                        btn.setText("Live")
                        style = btn.style()
                        if style is not None:
                            start_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
                            btn.setIcon(start_icon)
                    btn.disconnect()
                    btn.pressed.connect(lambda camera=camera_name: self._setup_live(camera_name))

            wgt.live_button.pressed.connect(lambda button=wgt.live_button: disable_button(button))
            wgt.live_button.pressed.connect(_configure_live_button)

            # Add functionality to the edges button
            def _enable_alignment_mode(self) -> None:
                if not self.grab_frames_worker and not self.grab_frames_worker.is_running:
                    self.log.warning("Could not enable alignment mode: grab frames worker is not running.")
                    return

                self.viewer.layers.clear()

                if self.alignment_button is not None and self.alignment_button.isChecked():
                    self.grab_frames_worker.yielded.disconnect()
                    self.grab_frames_worker.yielded.connect(self._dissect_image)
                else:
                    self.grab_frames_worker.yielded.disconnect()
                    self.grab_frames_worker.yielded.connect(self._update_layer)

            wgt.alignment_button.setCheckable(True)
            wgt.alignment_button.released.connect(_enable_alignment_mode)
            wgt.alignment_button.setDisabled(True)  # disable alignment button

            # Add functionality to the crosshairs button
            wgt.crosshairs_button.setCheckable(True)
            wgt.crosshairs_button.setDisabled(True)  # disable crosshairs button

        return camera_widgets

    def _create_daq_widgets(self) -> dict[str, NIWidget]:
        daq_widgets = {}
        for daq_name, daq in self.instrument.daqs.items():
            daq_widget = NIWidget(daq=daq, advanced_user=True)
            daq_widgets[daq_name] = daq_widget
        return daq_widgets

    def _create_filter_wheel_widgets(self) -> dict[str, FilterWheelWidget]:
        filter_wheel_widgets = {}
        for fw_name, fw in self.instrument.filter_wheels.items():
            fw_widget = FilterWheelWidget(filter_wheel=fw, advanced_user=True)
            filter_wheel_widgets[fw_name] = fw_widget
        return filter_wheel_widgets

    def _create_flip_mount_widgets(self) -> dict[str, FlipMountWidget]:
        flip_mount_widgets = {}
        for fm_name, fm in self.instrument.flip_mounts.items():
            fm_widget = FlipMountWidget(flip_mount=fm)
            flip_mount_widgets[fm_name] = fm_widget
        return flip_mount_widgets

    def _create_channels_widget(self) -> tuple[QWidget, QComboBox]:
        def _change_channel(channel: str):
            if self.grab_frames_worker.is_running:  # livestreaming is going
                for old_laser_name in self.instrument.channels[self.livestream_channel].get("lasers", []):
                    self.log.info(f"Disabling laser {old_laser_name}")
                    self.instrument.lasers[old_laser_name].disable()

                for daq_name, daq in self.instrument.daqs.items():
                    self.log.info(f"Writing new waveforms for {daq_name}")
                    if self.grab_frames_worker.is_running:  # if currently livestreaming
                        if daq.ao_task is not None:
                            daq.generate_waveforms("ao", self.livestream_channel)
                            daq.write_ao_waveforms(rereserve_buffer=False)
                        if daq.do_task is not None:
                            daq.generate_waveforms("do", self.livestream_channel)
                            daq.write_do_waveforms(rereserve_buffer=False)

                for new_laser_name in self.instrument.channels[channel].get("lasers", []):
                    self.log.info(f"Enabling laser {new_laser_name}")
                    self.instrument.lasers[new_laser_name].enable()

                self.livestream_channel = channel

                # change filter
                for filter in self.instrument.channels[self.livestream_channel].get("filters", []):
                    self.log.info(f"Enabling filter {filter}")
                    self.instrument.filters[filter].enable()
            else:
                self.log.warning(f"Cannot change channel to {channel} while livestreaming is active.")

        widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("Active Channel")
        laser_combo_box = QComboBox(widget)
        laser_combo_box.addItems(self.instrument.channels.keys())
        laser_combo_box.currentTextChanged.connect(lambda value: _change_channel(value))
        laser_combo_box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        laser_combo_box.setCurrentIndex(0)  # initialize to first channel index
        layout.addWidget(label)
        layout.addWidget(laser_combo_box)
        widget.setLayout(layout)
        widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        return widget, laser_combo_box

    def _configure_widget_props(self, widget: BaseDeviceWidget, device: VoxelDevice, device_name: str) -> None:
        # if gui is BaseDeviceWidget or inherits from it,
        # hook up widgets to device_property_changed when user changes value
        if isinstance(widget, BaseDeviceWidget):
            widget.ValueChangedInside[str].connect(
                lambda value, dev=device, widget=widget: self._device_property_changed(
                    attr_name=value, device=dev, widget=widget
                )
            )
            updating_props = (
                self.config["instrument_view"]["device_widgets"].get(device_name, {}).get("updating_properties", [])
            )
            for prop_name in updating_props:
                worker: WorkerBase = self._grab_property_value(
                    device=device,
                    property_name=prop_name,
                    device_widget=widget,
                )
                worker.yielded.connect(lambda args: self._update_property_value(*args))
                worker.start()
                self.property_workers[f"{device_name}_{prop_name}"] = worker

    def _stack_device_widgets(self, device_widgets: Mapping[str, QWidget]) -> QWidget:
        """
        Stack like device widgets in layout and hide/unhide with combo box
        :param device_type: type of device being stacked
        :return: widget containing all widgets pertaining to device type stacked ontop of each other
        """

        overlap_layout = QGridLayout()
        overlap_layout.addWidget(QWidget(), 1, 0)  # spacer widget
        for widget in device_widgets.values():
            widget.setVisible(False)
            overlap_layout.addWidget(widget, 2, 0)

        def _hide_devices(widgets: Mapping[str, QWidget], text: str) -> None:
            for name, widget in widgets.items():
                if name != text:
                    widget.setVisible(False)
                else:
                    widget.setVisible(True)

        visible = QComboBox()
        visible.currentTextChanged.connect(lambda text: _hide_devices(device_widgets, text))
        visible.addItems(device_widgets.keys())
        visible.setCurrentIndex(0)
        overlap_layout.addWidget(visible, 0, 0)

        overlap_widget = QWidget()
        overlap_widget.setLayout(overlap_layout)

        return overlap_widget

    def _create_device_widgets(self, device_name: str, device_specs: dict) -> None:
        """
        Create widgets based on device dictionary attributes from instrument or acquisition
         :param device_name: name of device
         :param device_specs: dictionary dictating how device should be set up
        """

        device_type = device_specs["type"]
        device = getattr(self.instrument, inflection.pluralize(device_type))[device_name]

        specs = self.config["instrument_view"]["device_widgets"].get(device_name, {})
        if specs != {} and specs.get("type", "") == device_type:
            gui_class = getattr(importlib.import_module(specs["driver"]), specs["module"])
            gui = gui_class(device, **specs.get("init", {}))  # device gets passed into widget
        else:
            properties = scan_for_properties(device)
            gui = BaseDeviceWidget(type(device), properties)

        self._configure_widget_props(widget=gui, device=device, device_name=device_name)

        # add ui to widget dictionary
        if not hasattr(self, f"{device_type}_widgets"):
            setattr(self, f"{device_type}_widgets", {})
        getattr(self, f"{device_type}_widgets")[device_name] = gui

        for subdevice_name, subdevice_specs in device_specs.get("subdevices", {}).items():
            # if device has subdevice, create and pass on same Lock()
            self._create_device_widgets(subdevice_name, subdevice_specs)

        gui.setWindowTitle(f"{device_type} {device_name}")

    # TODO: Inspect functionality
    def _add_undocked_widgets(self) -> None:
        """
        Add undocked widget so all windows close when closing napari viewer
        """

        widgets = []
        for key, dictionary in self.__dict__.items():
            if "_widgets" in key:
                widgets.extend(dictionary.values())
        for widget in widgets:
            if widget not in self.viewer.window._qt_window.findChildren(type(widget)):
                undocked_widget = self.viewer.window.add_dock_widget(widget, name=widget.windowTitle())
                undocked_widget.setFloating(True)
                # hide widget if empty property widgets
                if getattr(widget, "property_widgets", False) == {}:
                    undocked_widget.setVisible(False)

    def _update_property_value(self, value, device_widget, property_name: str) -> None:
        """
        Update stage position in stage widget
        :param device_widget: widget of entire device that is the parent of property widget
        :param value: value to update with
        :param property_name: name of property to set
        """
        with contextlib.suppress(RuntimeError, AttributeError):
            setattr(device_widget, property_name, value)  # setting attribute value will update widget

    def _update_config_on_quit(self) -> None:
        """
        Add functionality to close function to save device properties to instrument config
        """

        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Icon.Question)
        msgBox.setText(
            f"Do you want to update the instrument configuration file at {self.config_save_to} "
            f"to current instrument state?"
        )
        msgBox.setWindowTitle("Updating Configuration")
        msgBox.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        save_elsewhere = QPushButton("Change Directory")
        msgBox.addButton(save_elsewhere, QMessageBox.ButtonRole.DestructiveRole)

        def _select_directory(pressed: bool):
            fname = QFileDialog()
            folder = fname.getSaveFileName(directory=str(self.instrument.config_path))
            if folder[0] != "":  # user pressed cancel
                msgBox.setText(
                    f"Do you want to update the instrument configuration file at {folder[0]} to current instrument state?"
                )
                self.config_save_to = Path(folder[0])

        save_elsewhere.pressed.connect(lambda: _select_directory(True))

        return_value = msgBox.exec()
        if return_value == QMessageBox.StandardButton.Ok:
            self.instrument.update_current_state_config()
            self.instrument.save_config(self.config_save_to)

    def _toggle_live_button(self, camera_name: str) -> None:
        """
        Toggle text and functionality of live button when pressed
        :param camera_name: name of camera to set up
        """

        live_button = getattr(self.camera_widgets[camera_name], "live_button", QPushButton())
        live_button.disconnect()
        if live_button.text() == "Live":
            live_button.setText("Stop")
            style = live_button.style()
            if style is not None:
                stop_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
                live_button.setIcon(stop_icon)
            live_button.pressed.connect(self.grab_frames_worker.quit)
        else:
            live_button.setText("Live")
            style = live_button.style()
            if style is not None:
                start_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
                live_button.setIcon(start_icon)
            live_button.pressed.connect(lambda camera=camera_name: self._setup_live(camera_name))

        live_button.pressed.connect(lambda button=live_button: disable_button(button))
        live_button.pressed.connect(lambda camera=camera_name: self._toggle_live_button(camera_name))

    def _setup_live(self, camera_name: str, frames: int | None = None) -> None:
        """
        Set up for either livestream or snapshot
        :param camera_name: name of camera to set up
        :param frames: how many frames to take
        """

        layer_list = self.viewer.layers

        layer_name = self.livestream_channel

        # check if switching channels
        if layer_list and layer_name not in layer_list:
            self.viewer.layers.clear()

        if hasattr(self.grab_frames_worker, "is_running") and self.grab_frames_worker.is_running:
            if frames == 1 and f"{camera_name} {self.livestream_channel}" in self.viewer.layers:
                layer = self.viewer.layers[f"{camera_name} {self.livestream_channel}"]
                image = layer.data[0] if hasattr(layer, "multiscale") and layer.multiscale else layer.data
                self._update_layer((image, camera_name), snapshot=True)
            return

        self.grab_frames_worker = self.grab_frames(camera_name, frames)

        if frames == 1:  # pass in optional argument that this image is a snapshot
            if hasattr(self.grab_frames_worker, "yielded"):
                self.grab_frames_worker.yielded.connect(lambda args: self._update_layer(args, snapshot=True))
        else:
            if hasattr(self.grab_frames_worker, "yielded"):
                self.grab_frames_worker.yielded.connect(lambda args: self._update_layer(args))

        self.grab_frames_worker.finished.connect(lambda: self._dismantle_live(camera_name))

        self.instrument.cameras[camera_name].prepare()
        self.instrument.cameras[camera_name].start(frames)

        self.grab_frames_worker.start()

        for laser in self.instrument.channels[self.livestream_channel].get("lasers", []):
            self.log.info(f"Enabling laser {laser}")
            self.instrument.lasers[laser].enable()
            for k, v in self.instrument.lasers.items():
                wgt = self.laser_widgets.get(k)
                if k == laser:
                    v.enable()
                    if wgt is not None:
                        wgt.setEnabled(True)
                else:
                    v.disable()
                    if wgt is not None:
                        wgt.setEnabled(False)

        for filter in self.instrument.channels[self.livestream_channel].get("filters", []):
            self.log.info(f"Enabling filter {filter}")
            self.instrument.filters[filter].enable()

        for light in self.instrument.indicator_lights:
            self.log.info(f"Enabling indicator light {light}")
            self.instrument.indicator_lights[light].enable()

        for daq_name, daq in self.instrument.daqs.items():
            if daq.tasks.get("ao_task", None) is not None:
                daq.add_task("ao")
                daq.generate_waveforms("ao", self.livestream_channel)
                daq.write_ao_waveforms()
            if daq.tasks.get("do_task", None) is not None:
                daq.add_task("do")
                daq.generate_waveforms("do", self.livestream_channel)
                daq.write_do_waveforms()
            if daq.tasks.get("co_task", None) is not None:
                pulse_count = daq.tasks["co_task"]["timing"].get("pulse_count", None)
                daq.add_task("co", pulse_count)

            daq.start()

        if (camera_widget := self.camera_widgets.get(camera_name)) is not None:
            camera_widget.snapshot_button.setDisabled(True)
            camera_widget.crosshairs_button.setDisabled(True)
            camera_widget.alignment_button.setDisabled(True)

        for wgt in self.filter_wheel_widgets.values():
            wgt.setDisabled(True)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(True)  # disable channel widget

    def _dismantle_live(self, camera_name: str) -> None:
        """
        Dismantle live view for the specified camera.

        :param camera_name: Camera name
        :type camera_name: str
        """
        self.instrument.cameras[camera_name].abort()
        for _, daq in self.instrument.daqs.items():
            # wait for daq tasks to finish - prevents devices from stopping in
            # unsafe state, i.e. lasers still on
            daq.co_task.stop() if daq.co_task is not None else None
            # sleep to allow last ao to play with 10% buffer
            time.sleep(1.0 / daq.co_frequency_hz * 1.1)
            # stop the ao task
            daq.ao_task.stop() if daq.ao_task is not None else None
            # close the tasks
            daq.co_task.close() if daq.co_task is not None else None
            daq.ao_task.close() if daq.ao_task is not None else None

        for laser in self.instrument.channels[self.livestream_channel].get("lasers", []):
            if wgt := self.laser_widgets.get(laser):
                wgt.setEnabled(True)
                wgt.setDisabled(False)

        for name, light in self.instrument.indicator_lights.items():
            light.disable()
            self.log.info(f"Disabling indicator light {name}")

        if (camera_widget := self.camera_widgets.get(camera_name)) is not None:
            camera_widget.snapshot_button.setDisabled(False)
            camera_widget.crosshairs_button.setDisabled(False)
            camera_widget.alignment_button.setDisabled(False)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(False)

        for wgt in self.filter_wheel_widgets.values():
            wgt.setDisabled(False)

    def _update_layer(self, args: tuple, snapshot: bool = False) -> None:
        """
        Update the image layer in the viewer.

        :param args: tuple containing image and camera name
        :param snapshot: Whether the image is a snapshot, defaults to False
        """

        (image, camera_name) = args

        # calculate centroid of image
        pixel_size_um = self.instrument.cameras[camera_name].sampling_um_px
        y_center_um = image[0].shape[0] // 2 * pixel_size_um
        x_center_um = image[0].shape[1] // 2 * pixel_size_um

        layer_list = self.viewer.layers

        if image is not None:
            layer_name = self.livestream_channel if not snapshot else f"{self.livestream_channel} snapshot"
            if not snapshot:
                if layer_name in layer_list:
                    layer = layer_list[layer_name]
                    layer.data = image
                    layer.scale = (pixel_size_um, pixel_size_um)
                    layer.translate = (-x_center_um, y_center_um)
                else:
                    # Store current camera state BEFORE adding image to prevent auto-fit
                    current_zoom = self.viewer.camera.zoom
                    current_center = self.viewer.camera.center

                    contrast_limits = self.contrast_limits[self.livestream_channel]
                    layer = self.viewer.add_image(
                        image,
                        name=layer_name,
                        contrast_limits=(contrast_limits[0], contrast_limits[1]),
                        scale=(pixel_size_um, pixel_size_um),
                        translate=(-x_center_um, y_center_um),
                        rotate=self.camera_rotation,
                    )

                    # connect contrast limits event
                    def _viewer_contrast_limits(self, event: Event) -> None:
                        if self.livestream_channel in self.viewer.layers:
                            self.contrast_limits[self.livestream_channel] = list(
                                self.viewer.layers[self.livestream_channel].contrast_limits
                            )

                    layer.events.contrast_limits.connect(_viewer_contrast_limits)

                    # Restore camera view to prevent window resizing, except for very first image
                    if hasattr(self, "viewer_initialized") and self.viewer_initialized:
                        self.viewer.camera.zoom = current_zoom
                        self.viewer.camera.center = current_center
                    else:
                        # For the first image, let it fit but mark as initialized
                        self.viewer_initialized = True

                    # only reset state if there is a previous layer, otherwise pass
                    if self.previous_layer:
                        self.viewer.camera.zoom = self.viewer_state["zoom"]
                        self.viewer.camera.center = self.viewer_state["center"]
                        self.viewer.camera.angles = self.viewer_state["angles"]
                    # update previous layer name
                    self.previous_layer = layer_name
                    layer.mouse_drag_callbacks.append(self.save_image)
                for layer in layer_list:
                    if layer.name == layer_name:
                        layer.selected = True
                        layer.visible = True
                    else:
                        layer.selected = False
                        layer.visible = False
            else:
                layer = self.viewer.add_image(
                    image[-1],
                    name=layer_name,
                    contrast_limits=(self.intensity_min, self.intensity_max),
                    scale=(
                        pixel_size_um * 2 ** (self.resolution_levels - 1),
                        pixel_size_um * 2 ** (self.resolution_levels - 1),
                    ),
                    translate=(-x_center_um, y_center_um),
                    rotate=self.camera_rotation,
                )
                self.snapshotTaken.emit(np.copy(np.rot90(image[-1], k=2)), layer.contrast_limits)
                layer.selected = False
                layer.visible = False

    def _dissect_image(self, args: tuple) -> None:
        """
        Dissect the image and add to the viewer.

        :param args: Tuple containing image and camera name
        :type args: tuple
        """
        (image, camera_name) = args

        # calculate centroid of image
        pixel_size_um = self.instrument.cameras[camera_name].sampling_um_px
        y_center_um = image[0].shape[0] // 2 * pixel_size_um
        x_center_um = image[1].shape[1] // 2 * pixel_size_um

        if image is not None:
            # Dissect image and add to viewer
            alignment_roi = self.alignment_roi_size
            combined_roi = np.zeros((alignment_roi * 3, alignment_roi * 3))
            # top left corner
            top_left = image[0][0:alignment_roi, 0:alignment_roi]
            combined_roi[0:alignment_roi, 0:alignment_roi] = top_left
            # top right corner
            top_right = image[0][0:alignment_roi, -alignment_roi:]
            combined_roi[0:alignment_roi, alignment_roi * 2 : alignment_roi * 3] = top_right
            # bottom left corner
            bottom_left = image[0][-alignment_roi:, 0:alignment_roi]
            combined_roi[alignment_roi * 2 : alignment_roi * 3, 0:alignment_roi] = bottom_left
            # bottom right corner
            bottom_right = image[0][-alignment_roi:, -alignment_roi:]
            combined_roi[alignment_roi * 2 : alignment_roi * 3, alignment_roi * 2 : alignment_roi * 3] = bottom_right
            # center left
            center_left = image[0][
                round((image[0].shape[0] / 2) - alignment_roi / 2) : round((image[0].shape[0] / 2) + alignment_roi / 2),
                0:alignment_roi,
            ]
            combined_roi[alignment_roi : alignment_roi * 2, 0:alignment_roi] = center_left
            # center right
            center_right = image[0][
                round((image[0].shape[0] / 2) - alignment_roi / 2) : round((image[0].shape[0] / 2) + alignment_roi / 2),
                -alignment_roi:,
            ]
            combined_roi[alignment_roi : alignment_roi * 2, alignment_roi * 2 : alignment_roi * 3] = center_right
            # center top
            center_top = image[0][
                0:alignment_roi,
                round((image[0].shape[1] / 2) - alignment_roi / 2) : round((image[0].shape[1] / 2) + alignment_roi / 2),
            ]
            combined_roi[0:alignment_roi, alignment_roi : alignment_roi * 2] = center_top
            # center bottom
            center_bottom = image[0][
                -alignment_roi:,
                round((image[0].shape[1] / 2) - alignment_roi / 2) : round((image[0].shape[1] / 2) + alignment_roi / 2),
            ]
            combined_roi[alignment_roi * 2 : alignment_roi * 3, alignment_roi : alignment_roi * 2] = center_bottom
            # center roi
            center = image[0][
                round((image[0].shape[0] / 2) - alignment_roi / 2) : round((image[0].shape[0] / 2) + alignment_roi / 2),
                round((image[0].shape[1] / 2) - alignment_roi / 2) : round((image[0].shape[1] / 2) + alignment_roi / 2),
            ]
            combined_roi[alignment_roi : alignment_roi * 2, alignment_roi : alignment_roi * 2] = center

            # add crosshairs to image
            combined_roi[alignment_roi - 2 : alignment_roi + 2, :] = 1 << 16 - 1
            combined_roi[alignment_roi * 2 - 2 : alignment_roi * 2 + 2, :] = 1 << 16 - 1
            combined_roi[:, alignment_roi - 2 : alignment_roi + 2] = 1 << 16 - 1
            combined_roi[:, alignment_roi * 2 - 2 : alignment_roi * 2 + 2] = 1 << 16 - 1

            layer_name = f"{self.livestream_channel} alignment"
            if layer_name in self.viewer.layers:
                layer = self.viewer.layers[layer_name]
                layer.data = combined_roi
            else:
                layer = self.viewer.add_image(
                    combined_roi,
                    name=layer_name,
                    contrast_limits=(self.intensity_min, self.intensity_max),
                    scale=(pixel_size_um, pixel_size_um),
                    translate=(-x_center_um, y_center_um),
                    rotate=self.camera_rotation,
                )

    @Slot(str)
    def _device_property_changed(self, attr_name: str, device: Any, widget) -> None:
        """
        Slot to signal when device widget has been changed
        :param widget: widget object relating to device
        :param device: device object
        :param attr_name: name of attribute
        """

        name_lst = attr_name.split(".")
        self.log.debug(f"widget {attr_name} changed to {getattr(widget, name_lst[0])}")
        value = getattr(widget, name_lst[0])
        try:  # Make sure name is referring to same thing in UI and device
            dictionary = getattr(device, name_lst[0])
            for k in name_lst[1:]:
                dictionary = dictionary[k]

            # attempt to pass in correct value of correct type
            descriptor = getattr(type(device), name_lst[0])
            fset = getattr(descriptor, "fset")
            input_type = list(inspect.signature(fset).parameters.values())[-1].annotation
            if input_type != inspect._empty:
                setattr(device, name_lst[0], input_type(value))
            else:
                setattr(device, name_lst[0], value)

            self.log.info(f"Device changed to {getattr(device, name_lst[0])}")
            # Update ui with new device values that might have changed
            # WARNING: Infinite recursion might occur if device property not set correctly
            for k, v in widget.property_widgets.items():
                if getattr(widget, k, False):
                    device_value = getattr(device, k)
                    setattr(widget, k, device_value)

        except (KeyError, TypeError):
            self.log.warning(f"{attr_name} can't be mapped into device properties")
            pass

    @thread_worker
    def _grab_property_value(self, device: Any, property_name: str, device_widget) -> Iterator:
        """
        Grab value of property and yield
        :param device: device to grab property from
        :param property_name: name of property to get
        :param device_widget: widget of entire device that is the parent of property widget
        :return: value of property and widget to update
        """

        while True:  # best way to do this or have some sort of break?
            time.sleep(0.5)
            try:
                value = getattr(device, property_name)
            except ValueError:  # Tigerbox sometime coughs up garbage. Locking issue?
                value = None
            yield value, device_widget, property_name

    @thread_worker
    def grab_frames(
        self, camera_name: str, frames: int | None = None
    ) -> Generator[tuple[list[np.ndarray], str], None, None]:
        """
        Grab frames from camera
        :param frames: how many frames to take
        :param camera_name: name of camera
        """
        total_frames = frames if frames is not None else float("inf")
        i = 0
        while i < total_frames:  # while loop since frames can == inf
            time.sleep(0.5)
            multiscale = [self.instrument.cameras[camera_name].grab_frame()]
            for binning in range(1, self.resolution_levels):
                downsampled_frame = multiscale[-1][::2, ::2]
                multiscale.append(downsampled_frame)
            yield multiscale, camera_name
            i += 1

    def close(self) -> bool:
        """
        Close instruments and end threads
        """

        for worker in self.property_workers.values():
            if worker.is_running:
                worker.quit()
                while worker.is_running:
                    time.sleep(0.1)
        if self.grab_frames_worker.is_running:
            self.grab_frames_worker.quit()
            while self.grab_frames_worker.is_running:
                time.sleep(0.1)
        self.instrument.close()
        return True

    @staticmethod
    def save_image(layer: Image | list[Image], event: QMouseEvent) -> None:
        """
        Save image in viewer by right-clicking viewer
        :param layer: layer that was pressed
        :param event: mouse event
        """

        if event.button == 2:  # Left click
            # Handle both single layer and list of layers
            single_layer = layer[0] if isinstance(layer, list) else layer

            image = single_layer.data[0] if single_layer.multiscale else single_layer.data
            fname = QFileDialog()
            folder = fname.getSaveFileName(
                directory=str(
                    Path(__file__).parent.resolve()
                    / Path(rf"\{single_layer.name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.tiff")
                )
            )
            if folder[0] != "":  # user pressed cancel
                tifffile.imwrite(f"{folder[0]}.tiff", image, imagej=True)

    # def viewer_contrast_limits(self, event: Event) -> None:
    #     """Store viewer contrast limits anytime contrast limits change."""
    #     if self.livestream_channel in self.viewer.layers:
    #         self.contrast_limits[self.livestream_channel] = list(
    #             self.viewer.layers[self.livestream_channel].contrast_limits
    #         )
    # def set_button_to_stop_state(self, live_button, camera_name: str) -> None:
    #     """Set button to Stop state."""
    #     live_button.setText("Stop")
    #     style = self.style()
    #     if style is not None:
    #         live_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
    #     # Reconnect to stop functionality
    #     with contextlib.suppress(TypeError):
    #         live_button.pressed.disconnect()
    #     live_button.pressed.connect(lambda: self.toggle_live_button(camera_name))

    # def set_button_to_live_state(self, live_button, camera_name: str) -> None:
    #     """Set button to Live state."""
    #     live_button.setText("Live")
    #     style = self.style()
    #     if style is not None:
    #         live_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
    #     # Reconnect to live functionality
    #     with contextlib.suppress(TypeError):
    #         live_button.pressed.disconnect()
    #     live_button.pressed.connect(lambda: self.toggle_live_button(camera_name))

    # def stop_live_view(self, camera_name: str) -> None:
    #     """Stop the live view for the given camera."""
    #     if hasattr(self.grab_frames_worker, "is_running") and self.grab_frames_worker.is_running:
    #         # Stop the camera first
    #         if camera_name in self.instrument.cameras:
    #             try:
    #                 self.instrument.cameras[camera_name].stop()
    #             except Exception as e:
    #                 self.log.warning(f"Error stopping camera {camera_name}: {e}")

    #         # Then quit the worker - dismantle_live will be called by the finished signal
    #         self.grab_frames_worker.quit()

    # def _write_daq_waveforms(self, daq) -> None:
    #     """
    #     Write waveforms if livestreaming is on
    #     :param daq: daq object
    #     """

    #     if self.grab_frames_worker.is_running:  # if currently livestreaming
    #         if daq.ao_task is not None:
    #             daq.generate_waveforms("ao", self.livestream_channel)
    #             daq.write_ao_waveforms(rereserve_buffer=False)
    #         if daq.do_task is not None:
    #             daq.generate_waveforms("do", self.livestream_channel)
    #             daq.write_do_waveforms(rereserve_buffer=False)

    # def toggle_live_button(self, camera_name: str) -> None:
    #     """Toggle live button state for the given camera."""
    #     # Find the live button for this camera
    #     if camera_name in self.camera_widgets:
    #         camera_widget = self.camera_widgets[camera_name]
    #         live_button = getattr(camera_widget, "live_button", None)

    #         if live_button is not None:
    #             # Use button text to determine current state, not worker state
    #             current_text = live_button.text()

    #             if current_text == "Live":
    #                 # Change to Stop button and start live view
    #                 self.set_button_to_stop_state(live_button, camera_name)
    #                 self.setup_live(camera_name)
    #             else:
    #                 # Change to Live button and stop live view
    #                 self.set_button_to_live_state(live_button, camera_name)
    #                 self.stop_live_view(camera_name)
    # def camera_position(self, event: Event) -> None:
    #     """Store viewer state anytime camera moves and there is a layer."""
    #     if self.previous_layer and self.previous_layer in self.viewer.layers:
    #         self.viewer_state = {
    #             "zoom": self.viewer.camera.zoom,
    #             "center": self.viewer.camera.center,
    #             "angles": self.viewer.camera.angles,
    #         }

    # def camera_zoom(self, event: Event) -> None:
    #     """Store viewer state anytime camera zooms and there is a layer."""
    #     if self.previous_layer and self.previous_layer in self.viewer.layers:
    #         self.viewer_state = {
    #             "zoom": self.viewer.camera.zoom,
    #             "center": self.viewer.camera.center,
    #             "angles": self.viewer.camera.angles,
    #         }

    # def enable_alignment_mode(self) -> None:
    #     """
    #     Enable alignment mode.
    #     """
    #     if not self.grab_frames_worker and not self.grab_frames_worker.is_running:
    #         self.log.warning("Could not enable alignment mode: grab frames worker is not running.")
    #         return

    #     self.viewer.layers.clear()

    #     if self.alignment_button is not None and self.alignment_button.isChecked():
    #         self.grab_frames_worker.yielded.disconnect()
    #         self.grab_frames_worker.yielded.connect(self.dissect_image)
    #     else:
    #         self.grab_frames_worker.yielded.disconnect()
    #         self.grab_frames_worker.yielded.connect(self.update_layer)

    # def setup_camera_widgets(self) -> None:
    #     """
    #     Set up camera widgets.
    #     """
    #     for camera_name, camera_widget in self.camera_widgets.items():
    #         # Add functionality to snapshot button
    #         snapshot_button = getattr(camera_widget, "snapshot_button", None)
    #         if snapshot_button is not None:
    #             self.snapshot_button = snapshot_button
    #             snapshot_button.pressed.connect(
    #                 lambda button=snapshot_button: disable_button(button)
    #             )  # disable to avoid spamming
    #             snapshot_button.pressed.connect(lambda camera=camera_name: self.setup_live(camera, 1))

    #         # Add functionality to live button
    #         live_button = getattr(camera_widget, "live_button", None)
    #         if live_button is not None:
    #             live_button.pressed.connect(
    #                 lambda button=live_button: disable_button(button)
    #             )  # disable to avoid spamming
    #             live_button.pressed.connect(lambda camera=camera_name: self.setup_live(camera))
    #             live_button.pressed.connect(lambda camera=camera_name: self.toggle_live_button(camera))

    #         # Add functionality to the edges button
    #         alignment_button = getattr(camera_widget, "alignment_button", None)
    #         if alignment_button is not None:
    #             self.alignment_button = alignment_button
    #             alignment_button.setCheckable(True)
    #             alignment_button.released.connect(self.enable_alignment_mode)

    #         # Add functionality to the crosshairs button
    #         crosshairs_button = getattr(camera_widget, "crosshairs_button", None)
    #         if crosshairs_button is not None:
    #             self.crosshairs_button = crosshairs_button
    #             crosshairs_button.setCheckable(True)

    #         # Disable buttons if they exist
    #         if self.alignment_button is not None:
    #             self.alignment_button.setDisabled(True)  # disable alignment button
    #         if self.crosshairs_button is not None:
    #             self.crosshairs_button.setDisabled(True)  # disable crosshairs button

    #     stacked = self.stack_device_widgets("camera")
    #     self.viewer.window.add_dock_widget(stacked, area="right", name="Cameras", add_vertical_stretch=False)

    # def setup_filter_wheel_widgets(self) -> None:
    #     """
    #     Set up filter wheel widgets.
    #     """
    #     stacked = self.stack_device_widgets("filter_wheel")
    #     self.filter_wheel_widget = stacked
    #     self.viewer.window.add_dock_widget(stacked, area="right", name="Filter Wheels")

    # def setup_stage_widgets(self) -> None:
    #     """
    #     Set up stage widgets.
    #     """
    #     stage_widgets = []
    #     for name, widget in {
    #         **self.tiling_stage_widgets,
    #         **self.scanning_stage_widgets,
    #         **self.focusing_stage_widgets,
    #     }.items():
    #         label = QLabel()
    #         layout = QVBoxLayout()
    #         layout.addWidget(create_widget("H", label, widget))
    #         stage_widgets.append(layout)

    #     stage_axes_widget = create_widget("V", *stage_widgets)
    #     stage_axes_widget.setContentsMargins(0, 0, 0, 0)
    #     if stage_axes_widget.layout() is not None:
    #         stage_axes_widget.layout().setSpacing(6)  # type: ignore

    #     stage_scroll = QScrollArea()
    #     stage_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    #     stage_scroll.setWidget(stage_axes_widget)
    #     self.viewer.window.add_dock_widget(stage_axes_widget, area="left", name="Stages")

    # def setup_flip_mount_widgets(self) -> None:
    #     """
    #     Set up flip mount widgets.
    #     """
    #     stacked = self.stack_device_widgets("flip_mount")
    #     self.viewer.window.add_dock_widget(stacked, area="right", name="Flip Mounts")

    # def setup_laser_widgets(self) -> None:
    #     """
    #     Setup laser widgets.
    #     """
    #     laser_widgets = []
    #     for name, widget in self.laser_widgets.items():
    #         label = QLabel(name)
    #         layout = QVBoxLayout()
    #         layout.addWidget(create_widget("H", label, widget))
    #         laser_widgets.append(layout)
    #     self.laser_widget = create_widget("V", *laser_widgets)
    #     laser_layout = self.laser_widget.layout()
    #     if laser_layout is not None:
    #         laser_layout.setSpacing(12)
    #     self.viewer.window.add_dock_widget(self.laser_widget, area="bottom", name="Lasers")

    # def setup_channel_widget(self) -> None:
    #     """
    #     Create widget to select which laser to livestream with.
    #     """

    #     def _change_channel(channel: str):
    #         if self.grab_frames_worker.is_running:  # livestreaming is going
    #             for old_laser_name in self.instrument.channels[self.livestream_channel].get("lasers", []):
    #                 self.log.info(f"Disabling laser {old_laser_name}")
    #                 self.instrument.lasers[old_laser_name].disable()
    #             for daq_name, daq in self.instrument.daqs.items():
    #                 self.log.info(f"Writing new waveforms for {daq_name}")
    #                 self._write_daq_waveforms(daq)
    #             for new_laser_name in self.instrument.channels[channel].get("lasers", []):
    #                 self.log.info(f"Enabling laser {new_laser_name}")
    #                 self.instrument.lasers[new_laser_name].enable()

    #             self.livestream_channel = channel

    #             # change filter
    #             for filter in self.instrument.channels[self.livestream_channel].get("filters", []):
    #                 self.log.info(f"Enabling filter {filter}")
    #                 self.instrument.filters[filter].enable()
    #         else:
    #             self.log.warning(f"Cannot change channel to {channel} while livestreaming is active.")

    #     widget = QWidget()
    #     layout = QVBoxLayout()
    #     label = QLabel("Active Channel")
    #     laser_combo_box = QComboBox(widget)
    #     laser_combo_box.addItems(self.instrument.channels.keys())
    #     laser_combo_box.currentTextChanged.connect(lambda value: _change_channel(value))
    #     laser_combo_box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
    #     laser_combo_box.setCurrentIndex(0)  # initialize to first channel index
    #     self.laser_combo_box = laser_combo_box
    #     self.livestream_channel = laser_combo_box.currentText()  # initialize livestream channel
    #     layout.addWidget(label)
    #     layout.addWidget(laser_combo_box)
    #     widget.setLayout(layout)
    #     widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
    #     self.viewer.window.add_dock_widget(widget, area="bottom", name="Channels")

    # def change_channel(self, checked: bool, channel: str) -> None:
    #     """
    #     Change the livestream channel.

    #     :param checked: Whether the channel is checked
    #     :type checked: bool
    #     :param channel: Name of the channel
    #     :type channel: str
    #     """
    #     if not checked:  # Only process when channel is selected
    #         return

    #     if self.grab_frames_worker.is_running:  # livestreaming is going
    #         for old_laser_name in self.instrument.channels[self.livestream_channel].get("lasers", []):
    #             self.log.info(f"Disabling laser {old_laser_name}")
    #             self.instrument.lasers[old_laser_name].disable()
    #         for daq_name, daq in self.instrument.daqs.items():
    #             self.log.info(f"Writing new waveforms for {daq_name}")
    #             self._write_daq_waveforms(daq)
    #         for new_laser_name in self.instrument.channels[channel].get("lasers", []):
    #             self.log.info(f"Enabling laser {new_laser_name}")
    #             self.instrument.lasers[new_laser_name].enable()
    #     self.livestream_channel = channel
    #     # change filter
    #     for filter in self.instrument.channels[self.livestream_channel].get("filters", []):
    #         self.log.info(f"Enabling filter {filter}")
    #         self.instrument.filters[filter].enable()


class ExASPIMAcquisitionView(AcquisitionView):
    """Class for handling ExASPIM acquisition view."""

    acquisitionEnded = Signal()
    acquisitionStarted = Signal((datetime,))

    def __init__(self, acquisition: object, instrument_view: ExASPIMInstrumentView):
        """
        Initialize the ExASPIMAcquisitionView object.

        :param acquisition: Acquisition object
        :type acquisition: object
        :param instrument_view: Instrument view object
        :type instrument_view: ExASPIMInstrumentView
        """
        instrument_view.config["acquisition_view"]["unit"] = "mm"
        super().__init__(acquisition=acquisition, instrument_view=instrument_view)
        # acquisition view constants for ExA-SPIM
        self.binning_levels = 2
        self.acquisition_thread = create_worker(self.acquisition.run)
        # Eventual threads
        self.grab_frames_worker = create_worker(lambda: None)  # dummy thread
        self.setWindowTitle("ExA-SPIM control")

    def create_acquisition_widget(self):
        """
        Create the acquisition widget.

        :raises KeyError: If the coordinate plane does not match instrument axes in tiling_stages
        :return: Acquisition widget
        :rtype: QSplitter
        """
        # find limits of all axes
        lim_dict = {}
        # add tiling stages
        for name, stage in self.instrument.tiling_stages.items():
            lim_dict.update({f"{stage.instrument_axis}": stage.limits_mm})
        # last axis should be scanning axis
        ((scan_name, scan_stage),) = self.instrument.scanning_stages.items()
        lim_dict.update({f"{scan_stage.instrument_axis}": scan_stage.limits_mm})
        try:
            limits = [lim_dict[x.strip("-")] for x in self.coordinate_plane]
        except KeyError:
            raise KeyError("Coordinate plane must match instrument axes in tiling_stages")

        # TODO fix this, messy way to figure out FOV dimensions from camera properties
        first_camera_key = list(self.instrument.cameras.keys())[0]
        camera = self.instrument.cameras[first_camera_key]
        fov_height_mm = float(camera.fov_height_mm)
        fov_width_mm = float(camera.fov_width_mm)
        camera_rotation = self.config["instrument_view"]["properties"].get("camera_rotation_deg", 0)
        if camera_rotation in [-270, -90, 90, 270]:
            fov_dimensions: list[float] = [fov_height_mm, fov_width_mm, 0.0]
        else:
            fov_dimensions: list[float] = [fov_width_mm, fov_height_mm, 0.0]

        acquisition_widget = QSplitter(Qt.Orientation.Vertical)
        acquisition_widget.setChildrenCollapsible(False)

        # create volume plan
        self.volume_plan = VolumePlanWidget(
            instrument=self.instrument,
            limits=limits,
            fov_dimensions=fov_dimensions,
            coordinate_plane=self.coordinate_plane,
            unit=self.unit,
            default_overlap=self.config["acquisition_view"].get("default_overlap", 15.0),
            default_order=self.config["acquisition_view"].get("default_tile_order", "row_wise"),
        )
        self.volume_plan.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        # create volume model
        self.volume_model = VolumeModel(
            limits=limits,
            fov_dimensions=fov_dimensions,
            coordinate_plane=self.coordinate_plane,
            unit=self.unit,
            **self.config["acquisition_view"]["acquisition_widgets"].get("volume_model", {}).get("init", {}),
        )
        # combine floating volume_model widget with glwindow
        combined_layout = QGridLayout()
        combined_layout.addWidget(self.volume_model, 0, 0, 3, 1)
        combined_layout.addWidget(self.volume_model.widgets, 3, 0, 1, 1)
        combined = QWidget()
        combined.setLayout(combined_layout)
        acquisition_widget.addWidget(create_widget("H", self.volume_plan, combined))

        # create channel plan
        self.channel_plan = ChannelPlanWidget(
            instrument_view=self.instrument_view,
            channels=self.instrument.config["instrument"]["channels"],
            unit=self.unit,
            **self.config["acquisition_view"]["acquisition_widgets"].get("channel_plan", {}).get("init", {}),
        )
        # place volume_plan.tile_table and channel plan table side by side
        table_splitter = QSplitter(Qt.Orientation.Horizontal)
        table_splitter.setChildrenCollapsible(False)
        table_splitter.setHandleWidth(20)

        widget = QWidget()  # dummy widget to move tile_table down in layout
        widget.setMinimumHeight(25)
        table_splitter.addWidget(create_widget("V", widget, self.volume_plan.tile_table))
        table_splitter.addWidget(self.channel_plan)

        # format splitter handle. Must do after all widgets are added
        handle = table_splitter.handle(1)
        handle_layout = QHBoxLayout(handle)
        line = QFrame(handle)
        line.setStyleSheet("QFrame {border: 1px dotted grey;}")
        line.setFixedHeight(50)
        line.setFrameShape(QFrame.Shape.VLine)
        handle_layout.addWidget(line)

        # add tables to layout
        acquisition_widget.addWidget(table_splitter)

        # connect signals
        self.instrument_view.snapshotTaken.connect(self.volume_model.add_fov_image)  # connect snapshot signal
        self.instrument_view.contrastChanged.connect(
            self.volume_model.adjust_glimage_contrast
        )  # connect snapshot adjusted
        self.volume_model.fovHalt.connect(self.stop_stage)  # stop stage if halt button is pressed
        self.volume_model.fovMove.connect(self.move_stage)  # move stage to clicked coords
        self.volume_plan.valueChanged.connect(self.volume_plan_changed)
        self.channel_plan.channelAdded.connect(self.channel_plan_changed)
        self.channel_plan.channelChanged.connect(self.update_tiles)

        # TODO: This feels like a clunky connection. Works for now but could probably be improved
        self.volume_plan.header.startChanged.connect(lambda i: self.create_tile_list())
        self.volume_plan.header.stopChanged.connect(lambda i: self.create_tile_list())

        return acquisition_widget

    @thread_worker
    def grab_property_value(self, device: object, property_name: str, widget) -> Iterator:
        """
        Grab value of property and yield
        :param device: device to grab property from
        :param property_name: name of property to get
        :param widget: corresponding device widget
        :return: value of property and widget to update
        """

        while True:  # best way to do this or have some sort of break?
            time.sleep(1.0)
            value = getattr(device, property_name)
            yield value, widget

    def update_acquisition_layer(self, image: np.ndarray, camera_name: str) -> None:
        """
        Update the acquisition image layer in the viewer.

        :param image: Image array
        :type image: np.ndarray
        :param camera_name: Camera name
        :type camera_name: str
        """

        if image is not None:
            # for binning in range(0, self.binning_levels):
            #     image = self.instrument_view.downsampler.run(image)

            # calculate centroid of image
            pixel_size_um = self.instrument.cameras[camera_name].sampling_um_px
            y_center_um = image.shape[0] // 2 * pixel_size_um
            x_center_um = image.shape[1] // 2 * pixel_size_um

            layer_name = "acquisition"
            if layer_name in self.instrument_view.viewer.layers:
                layer = self.instrument_view.viewer.layers[layer_name]
                layer.data = image
                layer.scale = (pixel_size_um, pixel_size_um)
                layer.translate = (-x_center_um, y_center_um)
            else:
                layer = self.instrument_view.viewer.add_image(
                    image,
                    name=layer_name,
                    contrast_limits=(self.instrument_view.intensity_min, self.instrument_view.intensity_max),
                    scale=(pixel_size_um, pixel_size_um),
                    translate=(-x_center_um, y_center_um),
                    rotate=self.instrument_view.camera_rotation,
                )

    def save_acquisition(self) -> None:
        """
        Save a tile configuration to a YAML file.
        """

        # create YAML handler with non-aliasing representer
        yaml = YAML()
        yaml.Representer = NonAliasingRTRepresenter

        # save daq tasks to config
        daq = self.instrument.daqs[list(self.instrument.daqs.keys())[0]]
        self.acquisition.config["acquisition"]["daq"] = daq.tasks

        # save the tile configuration to the YAML file
        with open(f"{self.acquisition.metadata.acquisition_name}_tiles.yaml", "w") as file:
            yaml.dump(self.acquisition.config, file)

    def start_acquisition(self) -> None:
        """
        Start acquisition and disable widgets
        """

        # add tiles to acquisition config
        self.update_tiles()

        if self.instrument_view.grab_frames_worker.is_running:  # stop livestream if running
            self.instrument_view.grab_frames_worker.quit()

        # write correct daq values if different from livestream
        for daq_name, daq in self.instrument.daqs.items():
            if daq_name in self.config["acquisition_view"].get("data_acquisition_tasks", {}):
                daq.tasks = self.config["acquisition_view"]["data_acquisition_tasks"][daq_name]["tasks"]

        # anchor grid in volume widget
        for anchor, widget in zip(self.volume_plan.anchor_widgets, self.volume_plan.grid_offset_widgets):
            anchor.setChecked(True)
            widget.setDisabled(True)
        self.volume_plan.tile_table.setDisabled(True)
        self.channel_plan.setDisabled(True)

        # disable acquisition view. Can't disable whole thing so stop button can be functional
        self.start_button.setEnabled(False)
        self.metadata_widget.setEnabled(False)
        for operation in ["writer", "transfer", "process", "routine"]:
            if hasattr(self, f"{operation}_dock"):
                getattr(self, f"{operation}_dock").setDisabled(True)
        self.stop_button.setEnabled(True)
        # disable instrument view
        self.instrument_view.setDisabled(True)

        # Start acquisition
        self.acquisition_thread = create_worker(self.acquisition.run)
        self.acquisition_thread.start()
        self.acquisition_thread.finished.connect(self.acquisition_ended)

        # start all workers
        for worker in self.property_workers:
            worker.resume()
            time.sleep(1)
        self.acquisitionStarted.emit(datetime.now())

    def stop_acquisition(self) -> None:
        """
        Stop the acquisition process.
        """
        self.acquisition_thread.quit()
        self.acquisition.stop_acquisition()

    def acquisition_ended(self) -> None:
        """
        Handle the end of the acquisition process.
        """
        super().acquisition_ended()
        self.acquisitionEnded.emit()

    def create_start_button(self):
        """
        Create the start button.

        :return: Start button
        :rtype: QPushButton
        """
        start = QPushButton("Start")
        start.clicked.connect(self.start_acquisition)
        start.setStyleSheet("background-color: #55a35d; color: black; border-radius: 10px;")
        return start

    def create_stop_button(self):
        """
        Create the stop button.

        :return: Stop button
        :rtype: QPushButton
        """
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_acquisition)
        stop.setStyleSheet("background-color: #a3555b; color: black; border-radius: 10px;")
        stop.setDisabled(True)
        return stop

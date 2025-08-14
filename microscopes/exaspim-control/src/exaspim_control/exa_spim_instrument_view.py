import contextlib
import importlib
import inspect
import logging
import time
from collections.abc import Generator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import inflection
import napari
import numpy as np
import tifffile
from napari.layers import Image
from napari.qt.threading import create_worker, GeneratorWorker, FunctionWorker
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
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml import RoundTripRepresenter
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


class ChannelInfo(TypedDict):
    """TypedDict for channel information."""

    lasers: list[str]
    cameras: list[str]
    focusing_stages: list[str]
    filters: list[str]


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
        self.log.info("Starting napari viewer...")
        self.viewer = napari.Viewer(title="ExA-SPIM control", ndisplay=2, axis_labels=("x", "y"))

        self.property_workers: dict[str, FunctionWorker] = {}
        self.grab_frames_worker: GeneratorWorker = create_worker(lambda: None)

        # Add widget groups ---------------------------------------------------

        # Left
        self.stages_widget: QScrollArea = self._create_stage_widgets_scroll_area()
        self.viewer.window.add_dock_widget(self.stages_widget, area="left", name="Stages", add_vertical_stretch=True)

        # Right
        self.camera_widgets: dict[str, CameraWidget] = self._create_camera_widgets()
        # Initialize the live_button state
        for camera_name in self.camera_widgets:
            self._set_camera_live_button_to_start(camera_name)
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
        self.channels_widget, self.laser_combo_box = self._create_channels_widget()
        self.viewer.window.add_dock_widget(self.channels_widget, area="bottom", name="Channels")
        self.livestream_channel = self.laser_combo_box.currentText()  # initialize livestream channel

        self.compound_laser_widget, self.laser_widgets = self._create_laser_widgets()
        self.viewer.window.add_dock_widget(self.compound_laser_widget, area="bottom", name="Lasers")

        for device_name, device_specs in self.instrument.config["instrument"]["devices"].items():
            device_type = device_specs["type"]
            if device_type not in ["camera", "laser", "daq", "flip_mount", "stage", "filter_wheel"]:
                self._create_device_widgets(device_name, device_specs)

        # add undocked widget so everything closes together
        self._add_undocked_widgets()

        # Set app events
        app = QApplication.instance()

        def _update_config_on_quit() -> None:
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

        if isinstance(app, QApplication):
            app.aboutToQuit.connect(_update_config_on_quit)
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

        def _update_fps(fps: float) -> None:
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

        def _camera_zoom(event: Event) -> None:
            """Store viewer state anytime camera zooms and there is a layer."""
            if self.previous_layer and self.previous_layer in self.viewer.layers:
                self.viewer_state = {
                    "zoom": self.viewer.camera.zoom,
                    "center": self.viewer.camera.center,
                    "angles": self.viewer.camera.angles,
                }

        def _camera_position(event: Event) -> None:
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

    @property
    def active_channel(self) -> ChannelInfo | None:
        """Get the active channel information."""
        if (channel := self.instrument.channels.get(self.livestream_channel)) is not None:
            return ChannelInfo(
                lasers=channel.get("lasers", []),
                cameras=channel.get("cameras", []),
                focusing_stages=channel.get("focusing_stages", []),
                filters=channel.get("filters", []),
            )

    def _create_laser_widgets(self) -> tuple[QWidget, dict[str, LaserWidget]]:
        laser_widgets = {}
        hframes: list[QFrame] = []
        devices_specs = self.instrument.config.get("instrument", {}).get("devices", {})
        for laser_name, laser in self.instrument.lasers.items():
            laser_color = devices_specs.get(laser_name, {}).get("color", "blue")
            laser_widget = LaserWidget(laser=laser, color=laser_color, advanced_user=True)
            self._configure_widget_props(widget=laser_widget, device=laser, device_name=laser_name)
            laser_widgets[laser_name] = laser_widget

            label = QLabel(laser_name)
            hframe = QFrame()
            layout = QVBoxLayout()
            layout.addWidget(create_widget("H", label, laser_widget))
            hframe.setLayout(layout)
            border_color = get_theme(self.viewer.theme).foreground
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
            wgt = StageWidget(stage=stage, advanced_user=False)
            self._configure_widget_props(widget=wgt, device=stage, device_name=stage_name)
            layout = QVBoxLayout()
            layout.addWidget(create_widget("H", QLabel(stage_name), wgt))
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
            wgt.snapshot_button.pressed.connect(lambda: self._setup_live(1))

            # Add functionality to the edges button
            def _enable_alignment_mode() -> None:
                if not self.grab_frames_worker and not self.grab_frames_worker.is_running:
                    self.log.warning("Could not enable alignment mode: grab frames worker is not running.")
                    return

                self.viewer.layers.clear()

                if wgt.alignment_button is not None and wgt.alignment_button.isChecked():
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

            self._configure_widget_props(wgt, camera, camera_name)

        return camera_widgets

    def _create_daq_widgets(self) -> dict[str, NIWidget]:
        daq_widgets = {}
        for daq_name, daq in self.instrument.daqs.items():
            daq_widget = NIWidget(daq=daq, advanced_user=True)
            self._configure_widget_props(widget=daq_widget, device=daq, device_name=daq_name)
            daq_widgets[daq_name] = daq_widget
        return daq_widgets

    def _create_filter_wheel_widgets(self) -> dict[str, FilterWheelWidget]:
        filter_wheel_widgets = {}
        for fw_name, fw in self.instrument.filter_wheels.items():
            fw_widget = FilterWheelWidget(filter_wheel=fw, advanced_user=True)
            self._configure_widget_props(widget=fw_widget, device=fw, device_name=fw_name)
            filter_wheel_widgets[fw_name] = fw_widget
        return filter_wheel_widgets

    def _create_flip_mount_widgets(self) -> dict[str, FlipMountWidget]:
        flip_mount_widgets = {}
        for fm_name, fm in self.instrument.flip_mounts.items():
            fm_widget = FlipMountWidget(flip_mount=fm)
            self._configure_widget_props(widget=fm_widget, device=fm, device_name=fm_name)
            flip_mount_widgets[fm_name] = fm_widget
        return flip_mount_widgets

    def _create_channels_widget(self) -> tuple[QWidget, QComboBox]:
        def _change_channel(channel: str):
            chan = self.instrument.channels.get(channel)
            if not self.grab_frames_worker.is_running and chan is not None:  # livestreaming is not going
                chan_filters = chan.get("filters", [])
                # change filter
                for filter in chan_filters:
                    self.log.info(f"Enabling filter {filter}")
                    self.instrument.filters[filter].enable()

                for daq_name, daq in self.instrument.daqs.items():
                    self.log.info(f"Writing new waveforms for {daq_name}")
                    if daq.ao_task is not None:
                        daq.generate_waveforms("ao", self.livestream_channel)
                        daq.write_ao_waveforms(rereserve_buffer=False)
                    if daq.do_task is not None:
                        daq.generate_waveforms("do", self.livestream_channel)
                        daq.write_do_waveforms(rereserve_buffer=False)

                self.livestream_channel = channel

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

        def _grab_property_value(property_name: str):
            while True:  # best way to do this or have some sort of break?
                time.sleep(0.5)
                try:
                    value = getattr(device, property_name)
                except ValueError:  # Tigerbox sometime coughs up garbage. Locking issue?
                    value = None
                yield value, widget, property_name

        def _update_property_value(self, value, property_name: str) -> None:
            with contextlib.suppress(RuntimeError, AttributeError):
                self.log.error(f"setting {property_name} to {value} for device: {device_name}")
                setattr(widget, property_name, value)  # setting attribute value will update widget

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
                worker: FunctionWorker = create_worker(_grab_property_value, prop_name)
                worker.yielded.connect(lambda args: _update_property_value(*args))
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

    def _setup_live(self, frames: int | None = None) -> None:
        """
        Set up for either livestream or snapshot
        :param frames: how many frames to take
        """
        chan_cameras = self.instrument.channels[self.livestream_channel].get("cameras", [])
        if len(chan_cameras) != 1:
            self.log.error(
                f"Cannot start live view for channel {self.livestream_channel} - expected 1 camera, got {len(chan_cameras)}"
            )
            return
        camera_name = chan_cameras[0]
        camera_device = self.instrument.cameras.get(camera_name, None)
        if not camera_device:
            self.log.error(
                f"Cannot start live view for channel {self.livestream_channel} - camera {camera_name} not found"
            )
            return
        chan_lasers = self.instrument.channels[self.livestream_channel].get("lasers", [])
        chan_filters = self.instrument.channels[self.livestream_channel].get("filters", [])
        self.log.info(
            f"Starting live view for channel {self.livestream_channel}: "
            f"camera: {camera_name} lasers: {chan_lasers} filters: {chan_filters}"
        )

        layer_list = self.viewer.layers

        layer_name = self.livestream_channel

        # check if switching channels
        if layer_list and layer_name not in layer_list:
            self.viewer.layers.clear()

        if self.grab_frames_worker.is_running:
            self.log.warning("Cannot start live view: grab frames worker is already running.")
            if frames == 1 and f"{camera_name} {self.livestream_channel}" in self.viewer.layers:
                layer = self.viewer.layers[f"{camera_name} {self.livestream_channel}"]
                image = layer.data[0] if hasattr(layer, "multiscale") and layer.multiscale else layer.data
                self._update_layer((image, camera_name), snapshot=True)
            for wgt in self.camera_widgets.values():
                self._set_camera_live_button_to_stop(wgt)
            return

        def _frame_grabber_generator() -> Generator[tuple[list[np.ndarray], str], None, None]:
            camera_device.prepare()
            camera_device.start(frames)
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

        self.grab_frames_worker = create_worker(_frame_grabber_generator)

        if frames == 1:  # pass in optional argument that this image is a snapshot
            if hasattr(self.grab_frames_worker, "yielded"):
                self.grab_frames_worker.yielded.connect(lambda args: self._update_layer(args, snapshot=True))
        else:
            if hasattr(self.grab_frames_worker, "yielded"):
                self.grab_frames_worker.yielded.connect(lambda args: self._update_layer(args))

        self.grab_frames_worker.finished.connect(camera_device.stop)
        self.grab_frames_worker.start()

        for k, wgt in self.camera_widgets.items():
            self._set_camera_live_button_to_stop(wgt)

        if (camera_widget := self.camera_widgets.get(camera_name)) is not None:
            camera_widget.snapshot_button.setDisabled(True)
            camera_widget.crosshairs_button.setDisabled(True)
            camera_widget.alignment_button.setDisabled(True)

        for k, v in self.instrument.lasers.items():
            if k in chan_lasers:
                self.log.info(f"Enabling laser {k}")
                v.enable()
                if (wgt := self.laser_widgets.get(k)) is not None:
                    wgt.setEnabled(True)
            else:
                self.log.info(f"Disabling laser {k}")
                v.disable()
                if (wgt := self.laser_widgets.get(k)) is not None:
                    wgt.setEnabled(False)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(True)  # disable channel widget

        for wgt in self.filter_wheel_widgets.values():  # disable filter wheel widgets
            wgt.setDisabled(True)

        for light in self.instrument.indicator_lights:
            self.log.info(f"Enabling indicator light {light}")
            self.instrument.indicator_lights[light].enable()

        for daq in self.instrument.daqs.values():
            if daq.tasks.get("ao_task") is not None:
                daq.add_task("ao")
                daq.generate_waveforms("ao", self.livestream_channel)
                daq.write_ao_waveforms()
            # if daq.tasks.get("do_task") is not None:
            #     daq.add_task("do")
            #     daq.generate_waveforms("do", self.livestream_channel)
            #     daq.write_do_waveforms()
            if daq.tasks.get("co_task") is not None:
                pulse_count = daq.tasks["co_task"]["timing"].get("pulse_count", None)
                daq.add_task("co", pulse_count)

            daq.start()

    def _dismantle_live(self) -> None:
        """Dismantle live view for the specified camera."""
        chan = self.active_channel
        if chan is None:
            self.log.error("Cannot dismantle live view: active channel is None.")
            return
        # camera_name = self.instrument.channels
        self.grab_frames_worker.quit()

        time.sleep(0.25)
        while self.grab_frames_worker.is_running:
            time.sleep(0.25)
            self.log.warning("Dismantle Live is waiting for grab_frames_worker to finish...")

        # self.instrument.cameras[camera_name].stop()
        for daq in self.instrument.daqs.values():
            # wait for daq tasks to finish - prevents devices from stopping in
            # unsafe state, i.e. lasers still on
            if (co := daq.co_task) is not None:
                co.stop()
                co.close()

            # sleep to allow last ao to play with 10% buffer
            time.sleep(1.0 / daq.co_frequency_hz * 1.1)

            if (ao := daq.ao_task) is not None:
                ao.stop()
                ao.close()

        for laser in self.instrument.lasers.values():
            laser.disable()

        for name, light in self.instrument.indicator_lights.items():
            light.disable()
            self.log.info(f"Disabling indicator light {name}")

        for camera_name in chan["cameras"]:
            self._set_camera_live_button_to_start(camera_name)
            if (camera_widget := self.camera_widgets.get(camera_name)) is not None:
                camera_widget.snapshot_button.setDisabled(False)
                camera_widget.crosshairs_button.setDisabled(False)
                camera_widget.alignment_button.setDisabled(False)

        for wgt in self.laser_widgets.values():
            wgt.setEnabled(True)
            wgt.setDisabled(False)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(False)

        for wgt in self.filter_wheel_widgets.values():
            wgt.setDisabled(False)

    def _set_camera_live_button_to_start(self, camera_name: str) -> None:
        """
        Set the live button of the specified camera to the start state.

        :param camera_name: Camera name
        :type camera_name: str
        """
        if (camera_widget := self.camera_widgets.get(camera_name)) is not None:
            live_btn = camera_widget.live_button
            live_btn.setEnabled(True)
            live_btn.setText("Live")
            style = live_btn.style()
            if style is not None:
                start_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
                live_btn.setIcon(start_icon)
            live_btn.pressed.connect(lambda: disable_button(live_btn))
            live_btn.pressed.connect(self._setup_live)

    def _set_camera_live_button_to_stop(self, widget: CameraWidget) -> None:
        # configure live_button to stop
        live_btn = widget.live_button
        live_btn.disconnect()

        live_btn.setText("Stop")
        style = live_btn.style()
        if style is not None:
            stop_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaStop)
            live_btn.setIcon(stop_icon)
        live_btn.pressed.connect(lambda: disable_button(live_btn))
        # live_btn.pressed.connect(self.grab_frames_worker.quit)
        live_btn.pressed.connect(self._dismantle_live)

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
                    def _viewer_contrast_limits(event: Event) -> None:
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

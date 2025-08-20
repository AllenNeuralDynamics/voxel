import logging
import time
from collections.abc import Generator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import napari
import numpy as np
import tifffile
from exaspim_control.instrument.exaspim_instrument import ExASPIM, ExASPIMChannel
from napari.layers import Image
from napari.qt.threading import WorkerBase, FunctionWorker, create_worker
from napari.utils.events import Event
from napari.utils.theme import get_theme
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml import RoundTripRepresenter
from voxel_classic.processes.downsample.gpu.gputools.rank_downsample_2d import GPUToolsRankDownSample2D
from vidgets.view.base_device_widget import create_widget
from vidgets.view.device_widgets.camera_widget import CameraWidget
from vidgets.view.device_widgets.filter_wheel_widget import FilterWheelWidget
from vidgets.view.device_widgets.flip_mount_widget import FlipMountWidget
from vidgets.view.device_widgets.laser_widget import LaserWidget
from vidgets.view.device_widgets.ni_widget import NIWidget
from vidgets.view.device_widgets.stage_widget import StageWidget


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


class _ViewerState(TypedDict):
    zoom: float
    center: tuple[float, float] | tuple[float, float, float]
    angles: tuple[float, float, float]


class ExASPIMInstrumentView(QWidget):
    """Class for handling ExASPIM instrument vidgets."""

    snapshotTaken = Signal(object, list)
    contrastChanged = Signal(object, list)

    def __init__(self, instrument: ExASPIM, config: dict[str, Any]) -> None:
        """
        Initialize the ExASPIMInstrumentView object.

        :param instrument: Instrument object
        :type instrument: Instrument
        :param config: Configuration dictionary. loaded from gui_config.yaml
        :type config: dict[str, Any]
        """
        super().__init__()

        self.instrument: ExASPIM = instrument

        if isinstance(self.instrument.log, logging.Logger):
            self.log = self.instrument.log.getChild("View")
        elif isinstance(self.instrument.log, logging.LoggerAdapter):
            self.log = self.instrument.log.logger.getChild("View")

        self.config: dict[str, Any] = config

        # Setup napari window
        self.log.info("Starting napari viewer...")
        self.viewer = napari.Viewer(title="ExA-SPIM control", ndisplay=2, axis_labels=("x", "y"))

        self.property_workers: dict[str, FunctionWorker] = {}
        self.grab_frames_worker: WorkerBase = create_worker(lambda: None)

        # Add widget groups ---------------------------------------------------

        # Left

        # Right
        self.camera_widget: CameraWidget = self._create_camera_widget()
        self.camera_widget.configure_live_button_to_start(callback=self._start_live_stream)

        self.stages_widget: QWidget = self._create_stages_widget()
        self.channels_widget, self.laser_combo_box = self._create_channel_switching_widget()
        self.laser_combo_box.setCurrentText(self.instrument.active_channel.name)

        self.daq_widget = NIWidget(daq=self.instrument.daq, advanced_user=False)
        self.filter_wheel_widget = FilterWheelWidget(filter_wheel=self.instrument.filter_wheel)
        self.flip_mount_widgets: dict[str, FlipMountWidget] = {
            k: FlipMountWidget(v) for k, v in self.instrument.flip_mounts.items()
        }

        self.viewer.window.add_dock_widget(
            self.camera_widget,
            area="right",
            name="Camera",
            add_vertical_stretch=False,
        ).setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        self.viewer.window.add_dock_widget(
            create_widget("V", self.laser_combo_box, self.filter_wheel_widget),
            area="right",
            name="Channel Switching",
            add_vertical_stretch=False,
        ).setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        self.viewer.window.add_dock_widget(
            self.stages_widget,
            area="right",
            name="Stages",
            add_vertical_stretch=True,
        ).setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        right_panel_widgets: list[QWidget] = [self.daq_widget]
        if self.flip_mount_widgets:
            right_panel_widgets.append(self._stack_device_widgets(self.flip_mount_widgets))

        # Create the fixed right control panel
        # self.viewer.window.add_dock_widget(
        #     create_widget("V", *right_panel_widgets),
        #     area="right",
        #     name="Control Widgets",
        #     add_vertical_stretch=True,
        # )

        # Bottom
        self.compound_laser_widget, self.laser_widgets = self._create_laser_widgets()
        self.viewer.window.add_dock_widget(
            self.compound_laser_widget,
            area="bottom",
            name="Lasers",
        ).setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)

        # for device_name, device in self.instrument.other_devices.items():
        #     device_specs = self.instrument.config.get("instrument", {}).get("devices", {}).get(device_name, {})
        #     if device_specs != {}:
        #         self._create_device_widgets(device_name, device_specs)

        # add undocked widget so everything closes together
        self._add_undocked_widgets()

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
        self.viewer_state: _ViewerState = {
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

        # Set app events
        app = QApplication.instance()

        def _update_config_on_quit() -> None:
            """
            Add functionality to close function to save device properties to instrument config
            """

            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Icon.Question)
            msgBox.setText(
                f"Do you want to update the instrument configuration file at {self._config_save_path} "
                f"to current instrument state?"
            )
            msgBox.setWindowTitle("Updating Configuration")
            msgBox.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
            save_elsewhere = QPushButton("Change Directory")
            msgBox.addButton(save_elsewhere, QMessageBox.ButtonRole.DestructiveRole)

            def _select_directory(pressed: bool):
                fname = QFileDialog()
                folder = fname.getSaveFileName(dir=str(self.instrument.config_path))
                if folder[0] != "":  # user pressed cancel
                    msgBox.setText(
                        f"Do you want to update the instrument configuration file at {folder[0]} to current instrument state?"
                    )
                    self._config_save_path = Path(folder[0])

            save_elsewhere.pressed.connect(lambda: _select_directory(True))

            return_value = msgBox.exec()
            if return_value == QMessageBox.StandardButton.Ok:
                self.instrument.update_current_state_config()
                self.instrument.save_config(self._config_save_path)

        if isinstance(app, QApplication):
            app.aboutToQuit.connect(_update_config_on_quit)
            self._config_save_path = self.instrument.config_path
            app.lastWindowClosed.connect(self.close)

    @property
    def active_channel(self) -> ExASPIMChannel:
        """Get the active channel information."""
        return self.instrument.active_channel

    @property
    def livestream_channel(self) -> str:
        return self.active_channel.name

    def _create_laser_widgets(self) -> tuple[QWidget, dict[str, LaserWidget]]:
        laser_widgets = {}
        hframes: list[QFrame] = []
        for laser_name, laser in self.instrument.lasers.items():
            laser_widget = LaserWidget(laser=laser)
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

    def _create_stages_widget(self) -> QWidget:
        xyz_widget = QVBoxLayout()
        title_label = QLabel("Positioning Stages")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        xyz_widget.addWidget(title_label)
        for stage_name, stage in self.instrument.scanning_stages.items() and self.instrument.tiling_stages.items():
            wgt = StageWidget(stage=stage, advanced_user=False)
            wgt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            xyz_widget.addWidget(create_widget("H", QLabel(stage_name), wgt))

        n_widget = QVBoxLayout()
        title_label = QLabel("Focusing Stages")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        n_widget.addWidget(title_label)

        for stage_name, stage in self.instrument.focusing_stages.items():
            wgt = StageWidget(stage=stage, advanced_user=False)
            wgt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            n_widget.addWidget(create_widget("H", QLabel(stage_name), wgt))

        stage_axes_widget = create_widget("V", xyz_widget, n_widget)

        return stage_axes_widget

    def _create_camera_widget(self) -> CameraWidget:
        camera = self.instrument.camera
        wgt = CameraWidget(camera=camera, advanced_user=True)

        def _enable_alignment_mode() -> None:
            # if not self.grab_frames_worker and not self.grab_frames_worker.is_running:
            #     self.log.warning("Could not enable alignment mode: grab frames worker is not running.")
            #     return

            self.viewer.layers.clear()

            if wgt.alignment_button is not None and wgt.alignment_button.isChecked():
                self.grab_frames_worker.yielded.disconnect()
                self.grab_frames_worker.yielded.connect(self._dissect_image)
            else:
                self.grab_frames_worker.yielded.disconnect()
                self.grab_frames_worker.yielded.connect(self._update_layer)

        wgt.alignment_button.released.connect(_enable_alignment_mode)
        wgt.alignment_button.setDisabled(True)
        wgt.crosshairs_button.setDisabled(True)
        wgt.snapshot_button.pressed.connect(self._take_snapshot)

        return wgt

    def _create_channel_switching_widget(self) -> tuple[QWidget, QComboBox]:
        def _change_channel(channel: str):
            chan = self.instrument.channels.get(channel)
            if chan is None:
                self.log.warning(f"Channel {channel} not found.")
                return
            if self.grab_frames_worker.is_running:
                self.log.warning(f"Cannot change channel to {channel} while livestreaming is active.")
            else:
                self.instrument.activate_channel(channel)

        widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("Active Channel")
        laser_combo_box = QComboBox(widget)
        laser_combo_box.addItems(list(self.instrument.channels.keys()))
        laser_combo_box.setCurrentText(next(iter(self.instrument.channels.keys()), ""))
        laser_combo_box.currentTextChanged.connect(lambda value: _change_channel(value))
        laser_combo_box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        laser_combo_box.setCurrentIndex(0)  # initialize to first channel index
        layout.addWidget(label)
        layout.addWidget(laser_combo_box)
        widget.setLayout(layout)
        widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        return widget, laser_combo_box

    def _stack_device_widgets(self, device_widgets: Mapping[str, QWidget]) -> QWidget:
        """
        Stack like device widgets in layout and hide/unhide with combo box
        :param device_widgets: Mapping of device names to their widget instances
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
        visible.addItems(list(device_widgets.keys()))
        visible.setCurrentIndex(0)
        overlap_layout.addWidget(visible, 0, 0)

        overlap_widget = QWidget()
        overlap_widget.setLayout(overlap_layout)

        return overlap_widget

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

    def _start_live_stream(self) -> None:
        self.grab_frames_worker = create_worker(lambda: self._run_live_stream())
        self.grab_frames_worker.yielded.connect(self._update_layer)
        self.grab_frames_worker.finished.connect(self._dismantle_live_stream)

        self.camera_widget.disable_action_buttons()

        # check if switching channels
        if self.viewer.layers and self.livestream_channel not in self.viewer.layers:
            self.viewer.layers.clear()
        self.instrument.camera.prepare()
        self.instrument.camera.start()  # TODO: Figure out snapshot

        chan_laser = self.instrument.channels[self.livestream_channel].laser

        for name, laser_device in self.instrument.lasers.items():
            if name != chan_laser:
                laser_device.disable()
            # else:
            #     laser_device.enable()

        for name, wgt in self.laser_widgets.items():
            wgt.setEnabled(True) if name is chan_laser else wgt.setEnabled(False)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(True)  # disable channel widget

        self.filter_wheel_widget.setDisabled(True)

        for light in self.instrument.indicator_lights:
            self.log.info(f"Enabling indicator light {light}")
            self.instrument.indicator_lights[light].enable()

        self.instrument.daq.configure_acq_waveforms(self.active_channel.name)
        self.instrument.daq.start()

        self.grab_frames_worker.start()

        self.camera_widget.configure_live_button_to_stop(callback=self._stop_live_stream)
        self.camera_widget.enable_action_buttons()
        self.log.info("Grabber setup complete - beginning to collect frames")

    def _stop_live_stream(self) -> None:
        self.grab_frames_worker.quit()

    def _take_snapshot(self) -> None:
        self.log.info("Taking snapshot is not yet implemented")

    def _run_live_stream(self) -> Generator[tuple[list[np.ndarray], str], None, None]:
        self.log.warning("Starting live stream...")
        total_frames = float("inf")
        i = 0
        while i < total_frames:  # while loop since frames can == inf
            time.sleep(0.5)
            multiscale = [self.instrument.camera.grab_frame()]
            for binning in range(1, self.resolution_levels):
                downsampled_frame = multiscale[-1][::2, ::2]
                multiscale.append(downsampled_frame)
            yield multiscale, self.instrument.camera.uid
            i += 1

    def _dismantle_live_stream(self, result=None) -> None:
        """Dismantle live view for the specified camera."""
        chan = self.active_channel
        if chan is None:
            self.log.error("Cannot dismantle live view: active channel is None.")
            return

        self.camera_widget.disable_action_buttons()

        self.instrument.camera.stop()

        for daq in self.instrument.daqs.values():
            daq.stop_acq_tasks()

        for laser in self.instrument.lasers.values():
            laser.disable()

        for name, light in self.instrument.indicator_lights.items():
            light.disable()
            self.log.info(f"Disabling indicator light {name}")

        for wgt in self.laser_widgets.values():
            wgt.setEnabled(True)
            wgt.setDisabled(False)

        if self.laser_combo_box is not None:
            self.laser_combo_box.setDisabled(False)

        self.filter_wheel_widget.setDisabled(False)

        self.camera_widget.configure_live_button_to_start(callback=self._start_live_stream)
        self.camera_widget.enable_action_buttons()

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
                    layer.scale = np.array([pixel_size_um, pixel_size_um])
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
                            live_stream_layer = self.viewer.layers[self.livestream_channel]
                            if isinstance(live_stream_layer, Image):
                                self.contrast_limits[self.livestream_channel] = list(live_stream_layer.contrast_limits)

                    if isinstance(layer, Image):
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
                    if isinstance(layer, Image):
                        layer.mouse_drag_callbacks.append(self.save_image)
                for layer in layer_list:
                    if layer.name == layer_name:
                        self.viewer.layers.selection = [layer]
                        layer.visible = True
                    else:
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
                if isinstance(layer, Image):
                    self.snapshotTaken.emit(np.copy(np.rot90(image[-1], k=2)), layer.contrast_limits)
                    self.viewer.layers.selection = [layer]
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
                dir=str(
                    Path(__file__).parent.resolve()
                    / Path(rf"\{single_layer.name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.tiff")
                )
            )
            if folder[0] != "":  # user pressed cancel
                tifffile.imwrite(f"{folder[0]}.tiff", np.array(image), imagej=True)

    # def _create_device_widgets(self, device_name: str, device_specs: dict) -> None:
    #     """
    #     Create widgets based on device dictionary attributes from instrument or acquisition
    #      :param device_name: name of device
    #      :param device_specs: dictionary dictating how device should be set up
    #     """

    #     device = self.instrument._devices.get(device_name, None)

    #     device_type_from_specs = device_specs.get("type", "other")

    #     specs = self.config["instrument_view"]["device_widgets"].get(device_name, {})
    #     if specs != {} and specs.get("type", "") == device_type_from_specs:
    #         gui_class = getattr(importlib.import_module(specs["driver"]), specs["module"])
    #         gui = gui_class(device, **specs.get("init", {}))  # device gets passed into widget
    #     else:
    #         properties = scan_for_properties(device)
    #         gui = BaseDeviceWidget(type(device), properties)

    #     if device is not None:
    #         self.property_workers.update(gui.attach_device(device))

    #     # add ui to widget dictionary
    #     if not hasattr(self, f"{device_type_from_specs}_widgets"):
    #         setattr(self, f"{device_type_from_specs}_widgets", {})
    #     getattr(self, f"{device_type_from_specs}_widgets")[device_name] = gui

    #     for subdevice_name, subdevice_specs in device_specs.get("subdevices", {}).items():
    #         # if device has subdevice, create and pass on same Lock()
    #         self._create_device_widgets(subdevice_name, subdevice_specs)

    #     gui.setWindowTitle(f"{device_type_from_specs} {device_name}")

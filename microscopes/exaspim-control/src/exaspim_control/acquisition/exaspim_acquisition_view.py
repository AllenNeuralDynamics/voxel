import time
from collections.abc import Iterator
from datetime import UTC, datetime

import inflection
import numpy as np
from exaspim_control.acquisition.exaspim_acquisition import ExASPIMAcquisition
from exaspim_control.instrument.exaspim_instrument_view import ExASPIMInstrumentView
from napari.qt import get_stylesheet
from napari.qt.threading import create_worker, thread_worker
from napari.settings import get_settings
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QWidget,
)
from ruamel.yaml import YAML, RoundTripRepresenter
from vidgets.view.acquisition_widgets.channel_plan_widget import ChannelPlanWidget
from vidgets.view.acquisition_widgets.metadata_widget import MetadataWidget
from vidgets.view.acquisition_widgets.volume_model import VolumeModel
from vidgets.view.acquisition_widgets.volume_plan_widget import (
    GridFromEdges,
    GridRowsColumns,
    GridWidthHeight,
    VolumePlanWidget,
)
from vidgets.view.base_device_widget import create_widget, scan_for_properties
from vidgets.view.miscellaneous_widgets.q_dock_widget_title_bar import QDockWidgetTitleBar
from voxel.utils.log import VoxelLogging


class NonAliasingRTRepresenter(RoundTripRepresenter):
    """Custom representer for ruamel.yaml to ignore aliases.
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


class ExASPIMAcquisitionView(QWidget):
    """Class for handling ExASPIM acquisition view with all merged functionality."""

    acquisitionEnded = Signal()
    acquisitionStarted = Signal(datetime)

    def __init__(self, acquisition: ExASPIMAcquisition, instrument_view: ExASPIMInstrumentView):
        """Initialize the ExASPIMAcquisitionView object.

        :param acquisition: Acquisition object
        :type acquisition: object
        :param instrument_view: Instrument view object
        :type instrument_view: ExASPIMInstrumentView
        :param log_level: level to set logger at
        """
        super().__init__()
        self.log = VoxelLogging.get_logger(obj=self)

        # Set ExASPIM-specific configuration
        instrument_view.config['acquisition_view']['unit'] = 'mm'

        # Remove the problematic napari.qt.get_current_stylesheet() call
        self.setStyleSheet(get_stylesheet(get_settings().appearance.theme))
        self.instrument_view = instrument_view
        self.acquisition = acquisition
        self.instrument = self.acquisition.instrument
        self.config = instrument_view.config
        self.coordinate_plane = self.config['acquisition_view']['coordinate_plane']
        self.unit = self.config['acquisition_view']['unit']

        # acquisition view constants for ExA-SPIM
        self.binning_levels = 2

        # Eventual threads
        self.grab_fov_positions_worker = None
        self.property_workers = []
        self.acquisition_thread = create_worker(self.acquisition.run)  # pyright: ignore[reportArgumentType]
        self.grab_frames_worker = create_worker(lambda: None)  # dummy thread

        # Create device widgets for operations
        self.writer_widgets = {}
        self.transfer_widgets = {}
        self.process_widgets = {}
        self.routine_widgets = {}

        # create workers for latest image taken by cameras
        for camera_name, camera in self.instrument.cameras.items():
            worker = create_worker(self.grab_property_value, camera, 'last_image', None)  # pyright: ignore[reportArgumentType]
            worker.yielded.connect(lambda x, camera_name=camera_name: self.update_acquisition_layer(x[0], camera_name))
            worker.start()
            worker.pause()  # pyright: ignore[reportCallIssue]
            self.property_workers.append(worker)

        for device_name, operation_dictionary in self.acquisition.config['acquisition']['operations'].items():
            for operation_name, operation_specs in operation_dictionary.items():
                self.create_operation_widgets(device_name, operation_name, operation_specs)

        # setup additional widgets
        self.metadata_widget = self.create_metadata_widget()
        self.acquisition_widget = self.create_acquisition_widget()
        self.start_button = self.create_start_button()
        self.stop_button = self.create_stop_button()
        self.save_button = self.create_save_button()

        # setup stage thread
        self.setup_fov_position()

        # Set up main window
        self.main_layout = QGridLayout()

        # Add start and stop button
        self.main_layout.addWidget(self.start_button, 0, 0, 1, 1)
        self.main_layout.addWidget(self.stop_button, 0, 1, 1, 1)
        self.main_layout.addWidget(self.save_button, 0, 2, 1, 1)

        # add volume widget
        self.main_layout.addWidget(self.acquisition_widget, 1, 0, 5, 3)

        # splitter for operation widgets
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # create scroll wheel for metadata widget
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.metadata_widget)
        scroll.setWindowTitle('Metadata')
        scroll.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        dock = QDockWidget(scroll.windowTitle(), self)
        dock.setWidget(scroll)
        dock.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        dock.setTitleBarWidget(QDockWidgetTitleBar(dock))
        dock.setWidget(scroll)
        dock.setMinimumHeight(25)
        splitter.addWidget(dock)

        # create dock widget for operations
        for _i, operation in enumerate(['writer', 'file_transfer', 'process', 'routine']):
            operation_name = operation if operation != 'file_transfer' else 'transfer'
            if hasattr(self, f'{operation_name}_widgets') and getattr(self, f'{operation_name}_widgets'):
                operation_widget = self.stack_device_widgets(operation_name)
                scroll = QScrollArea()
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                scroll.setWidget(operation_widget)
                scroll.setWindowTitle(operation_widget.windowTitle())
                scroll.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
                dock = QDockWidget(scroll.windowTitle(), self)
                dock.setWidget(scroll)
                dock.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
                dock.setTitleBarWidget(QDockWidgetTitleBar(dock))
                dock.setWidget(scroll)
                dock.setMinimumHeight(25)
                setattr(self, f'{operation_name}_dock', dock)
                splitter.addWidget(dock)

        self.main_layout.addWidget(splitter, 1, 3)
        self.setLayout(self.main_layout)
        self.setWindowTitle('ExA-SPIM control')
        self.show()

        # Set app events
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.update_config_on_quit)

    def create_start_button(self) -> QPushButton:
        """Create the start button.

        :return: Start button
        :rtype: QPushButton
        """
        start = QPushButton('Start')
        start.clicked.connect(self.start_acquisition)
        start.setStyleSheet('background-color: #55a35d; color: black; border-radius: 10px;')
        return start

    def create_stop_button(self) -> QPushButton:
        """Create the stop button.

        :return: Stop button
        :rtype: QPushButton
        """
        stop = QPushButton('Stop')
        stop.clicked.connect(self.stop_acquisition)
        stop.setStyleSheet('background-color: #a3555b; color: black; border-radius: 10px;')
        stop.setDisabled(True)
        return stop

    def create_save_button(self) -> QPushButton:
        """Create the save button.

        :return: Save button
        :rtype: QPushButton
        """
        save = QPushButton('Save')
        save.clicked.connect(self.save_acquisition)
        save.setStyleSheet('background-color: #ffca33; color: black; border-radius: 10px;')
        return save

    def stop_acquisition(self) -> None:
        """Stop the acquisition process."""
        if hasattr(self, 'acquisition_thread'):
            self.acquisition_thread.quit()
        self.acquisition.stop_acquisition()
        self.acquisition_ended()

    def save_acquisition(self) -> None:
        """Save a tile configuration to a YAML file."""
        # create YAML handler with non-aliasing representer
        yaml = YAML()
        yaml.Representer = NonAliasingRTRepresenter

        # save daq tasks to config
        daq = self.instrument.daqs[next(iter(self.instrument.daqs.keys()))]
        self.acquisition.config['acquisition']['daq'] = daq.tasks

        # save the tile configuration to the YAML file
        if self.acquisition.metadata is not None:
            with open(f'{self.acquisition.metadata.acquisition_name}_tiles.yaml', 'w') as file:
                yaml.dump(self.acquisition.config, file)

    def start_acquisition(self) -> None:
        """Start acquisition and disable widgets."""
        # add tiles to acquisition config
        self.update_tiles()

        if self.instrument_view.grab_frames_worker.is_running:  # stop livestream if running
            self.instrument_view.grab_frames_worker.quit()

        # write correct daq values if different from livestream
        for daq_name, daq in self.instrument.daqs.items():
            if daq_name in self.config['acquisition_view'].get('data_acquisition_tasks', {}):
                daq.tasks = self.config['acquisition_view']['data_acquisition_tasks'][daq_name]['tasks']

        # anchor grid in volume widget
        for anchor, widget in zip(self.volume_plan.anchor_widgets, self.volume_plan.grid_offset_widgets, strict=False):
            anchor.setChecked(True)
            widget.setDisabled(True)
        self.volume_plan.tile_table.setDisabled(True)
        self.channel_plan.setDisabled(True)

        # disable acquisition vidgets. Can't disable whole thing so stop button can be functional
        self.start_button.setEnabled(False)
        self.metadata_widget.setEnabled(False)
        for operation in ['writer', 'transfer', 'process', 'routine']:
            if hasattr(self, f'{operation}_dock'):
                getattr(self, f'{operation}_dock').setDisabled(True)
        self.stop_button.setEnabled(True)
        # disable instrument view
        self.instrument_view.setDisabled(True)

        # Start acquisition
        self.instrument_view.setDisabled(False)
        self.acquisition_thread = create_worker(self.acquisition.run)  # pyright: ignore[reportArgumentType]
        self.acquisition_thread.start()
        self.acquisition_thread.finished.connect(self.acquisition_ended)  # pyright: ignore[reportArgumentType]

        # start all workers
        for worker in self.property_workers:
            worker.resume()
            time.sleep(1)
        self.acquisitionStarted.emit(datetime.now(UTC))

    def acquisition_ended(self) -> None:
        """Handle the end of the acquisition process."""
        # enable acquisition view
        self.start_button.setEnabled(True)
        self.metadata_widget.setEnabled(True)
        for operation in ['writer', 'transfer', 'process', 'routine']:
            if hasattr(self, f'{operation}_dock'):
                getattr(self, f'{operation}_dock').setDisabled(False)
        self.stop_button.setEnabled(False)

        # write correct daq values if different from acquisition task
        for daq_name, daq in self.instrument.daqs.items():
            if daq_name in self.config['instrument_view'].get('data_acquisition_tasks', {}):
                daq.tasks = self.config['instrument_view']['data_acquisition_tasks'][daq_name]['tasks']

        # unanchor grid in volume widget
        for anchor, widget in zip(self.volume_plan.anchor_widgets, self.volume_plan.grid_offset_widgets, strict=False):
            anchor.setChecked(False)
            widget.setDisabled(False)
        self.volume_plan.tile_table.setDisabled(False)
        self.channel_plan.setDisabled(False)

        # enable instrument view
        self.instrument_view.setDisabled(False)

        # restart stage threads
        self.setup_fov_position()

        for worker in self.property_workers:
            worker.pause()

        self.acquisitionEnded.emit()

    def stack_device_widgets(self, device_type: str) -> QWidget:
        """Stack like device widgets in layout and hide/unhide with combo box
        :param device_type: type of device being stacked
        :return: widget containing all widgets pertaining to device type stacked ontop of each other.
        """
        device_widgets = {
            f'{inflection.pluralize(device_type)} {device_name}': create_widget('V', **widgets)
            for device_name, widgets in getattr(self, f'{device_type}_widgets').items()
        }

        overlap_layout = QGridLayout()
        overlap_layout.addWidget(QWidget(), 1, 0)  # spacer widget
        for widget in device_widgets.values():
            widget.hide()
            overlap_layout.addWidget(widget, 1, 0)

        visible = QComboBox()
        visible.currentTextChanged.connect(lambda text: self.hide_devices(text, device_widgets))
        visible.addItems(list(device_widgets.keys()))
        visible.setCurrentIndex(0)
        overlap_layout.addWidget(visible, 0, 0)

        overlap_widget = QWidget()
        overlap_widget.setWindowTitle(inflection.pluralize(device_type))
        overlap_widget.setLayout(overlap_layout)

        return overlap_widget

    @staticmethod
    def hide_devices(text: str, device_widgets: dict) -> None:
        """Hide all devices except the selected one."""
        for name, widget in device_widgets.items():
            widget.setVisible(name == text)

    def create_metadata_widget(self) -> MetadataWidget:
        """Create custom widget for metadata in config
        :return: widget for metadata.
        """
        metadata_widget = MetadataWidget(self.acquisition.metadata)
        metadata_widget.ValueChangedInside.connect(
            lambda name: setattr(self.acquisition.metadata, name, getattr(metadata_widget, name)),
        )
        for name, widget in metadata_widget.property_widgets.items():
            property_worker = create_worker(self.grab_property_value, self.acquisition.metadata, name, widget)  # pyright: ignore[reportArgumentType]
            property_worker.yielded.connect(lambda x: self.update_property_value(x[0], x[1]))
            property_worker.start()
            property_worker.pause()  # pyright: ignore[reportCallIssue]
            self.property_workers.append(property_worker)
        metadata_widget.setWindowTitle('Metadata')
        return metadata_widget

    def create_acquisition_widget(self) -> QSplitter:
        """Create the acquisition widget.

        :raises KeyError: If the coordinate plane does not match instrument axes in tiling_stages
        :return: Acquisition widget
        :rtype: QSplitter
        """
        # find limits of all axes
        lim_dict = {}
        # add tiling stages
        for stage in self.instrument.tiling_stages.values():
            lim_dict.update({f'{stage.instrument_axis}': stage.limits_mm})
        # last axis should be scanning axis
        ((scan_name, scan_stage),) = self.instrument.scanning_stages.items()
        lim_dict.update({f'{scan_stage.instrument_axis}': scan_stage.limits_mm})
        try:
            limits = [lim_dict[x.strip('-')] for x in self.coordinate_plane]
        except KeyError as e:
            raise KeyError('Coordinate plane must match instrument axes in tiling_stages') from e

        # TODO fix this, messy way to figure out FOV dimensions from camera properties
        first_camera_key = next(iter(self.instrument.cameras.keys()))
        camera = self.instrument.cameras[first_camera_key]
        fov_height_mm = float(camera.fov_height_mm)
        fov_width_mm = float(camera.fov_width_mm)
        camera_rotation = self.config['instrument_view']['properties'].get('camera_rotation_deg', 0)
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
            default_overlap=self.config['acquisition_view'].get('default_overlap', 15.0),
            default_order=self.config['acquisition_view'].get('default_tile_order', 'row_wise'),
        )
        self.volume_plan.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)

        # create volume model
        self.volume_model = VolumeModel(
            limits=limits,
            fov_dimensions=fov_dimensions,
            coordinate_plane=self.coordinate_plane,
            unit=self.unit,
            **self.config['acquisition_view']['acquisition_widgets'].get('volume_model', {}).get('init', {}),
        )
        # combine floating volume_model widget with glwindow
        combined_layout = QGridLayout()
        combined_layout.addWidget(self.volume_model, 0, 0, 3, 1)
        combined_layout.addWidget(self.volume_model.widgets, 3, 0, 1, 1)
        combined = QWidget()
        combined.setLayout(combined_layout)
        acquisition_widget.addWidget(create_widget('H', self.volume_plan, combined))

        # create channel plan
        self.channel_plan = ChannelPlanWidget(
            instrument_view=self.instrument_view,
            channels=self.instrument.config['instrument']['channels'],
            unit=self.unit,
            **self.config['acquisition_view']['acquisition_widgets'].get('channel_plan', {}).get('init', {}),
        )
        # place volume_plan.tile_table and channel plan table side by side
        table_splitter = QSplitter(Qt.Orientation.Horizontal)
        table_splitter.setChildrenCollapsible(False)
        table_splitter.setHandleWidth(20)

        widget = QWidget()  # dummy widget to move tile_table down in layout
        widget.setMinimumHeight(25)
        table_splitter.addWidget(create_widget('V', widget, self.volume_plan.tile_table))
        table_splitter.addWidget(self.channel_plan)

        # format splitter handle. Must do after all widgets are added
        handle = table_splitter.handle(1)
        handle_layout = QHBoxLayout(handle)
        line = QFrame(handle)
        line.setStyleSheet('QFrame {border: 1px dotted grey;}')
        line.setFixedHeight(50)
        line.setFrameShape(QFrame.Shape.VLine)
        handle_layout.addWidget(line)

        # add tables to layout
        acquisition_widget.addWidget(table_splitter)

        # connect signals
        self.instrument_view.snapshotTaken.connect(self.volume_model.add_fov_image)  # connect snapshot signal
        self.instrument_view.contrastChanged.connect(
            self.volume_model.adjust_glimage_contrast,
        )  # connect snapshot adjusted
        self.volume_model.fovHalt.connect(self.stop_stage)  # stop stage if halt button is pressed
        self.volume_model.fovMove.connect(self.move_stage)  # move stage to clicked coords
        self.volume_plan.valueChanged.connect(self.volume_plan_changed)
        self.channel_plan.channelAdded.connect(self.channel_plan_changed)
        self.channel_plan.channelChanged.connect(self.update_tiles)

        # TODO: This feels like a clunky connection. Works for now but could probably be improved
        self.volume_plan.header.startChanged.connect(lambda: self.create_tile_list())
        self.volume_plan.header.stopChanged.connect(lambda: self.create_tile_list())

        return acquisition_widget

    def channel_plan_changed(self, channel: str) -> None:
        """Handle channel plan changes."""
        self.volume_model.add_channel(channel)
        self.update_tiles()

    def volume_plan_changed(self, value: GridRowsColumns | GridFromEdges | GridWidthHeight) -> None:
        """Handle volume plan changes."""
        # Extract positions from the grid object's iter_grid_positions method
        positions = list(value.iter_grid_positions())
        self.volume_model.set_fov_positions(positions)

    def update_tiles(self) -> None:
        """Update tiles configuration."""
        self.acquisition.config['acquisition']['tiles'] = self.create_tile_list()

    def move_stage(self, fov_position: list[float]) -> None:
        """Move stage to specified FOV position."""
        for axis, position in zip(self.coordinate_plane[:2], fov_position, strict=False):
            stage_name = axis.strip('-')
            if stage_name in self.instrument.stage.axes_names:
                stage = self.instrument.stage[stage_name]
                stage.position_mm = position

    def stop_stage(self) -> None:
        """Stop all stage movement."""
        self.instrument.stage.stop()

    def setup_fov_position(self) -> None:
        """Setup FOV position monitoring."""
        if hasattr(self, 'grab_fov_positions_worker') and self.grab_fov_positions_worker is not None:
            self.grab_fov_positions_worker.quit()

        self.grab_fov_positions_worker = create_worker(self.grab_fov_positions)  # pyright: ignore[reportArgumentType]
        self.grab_fov_positions_worker.yielded.connect(self.volume_model.set_current_fov_position)
        self.grab_fov_positions_worker.start()

    @thread_worker
    def grab_fov_positions(self) -> Iterator:
        """Grab current FOV positions from stages."""
        while True:
            time.sleep(0.1)
            positions = []
            for axis in self.coordinate_plane[:2]:
                stage_name = axis.strip('-')
                if stage_name in self.instrument.stage.axes_names:
                    stage = self.instrument.stage[stage_name]
                    position = stage.position_mm
                    if position and axis.startswith('-'):
                        position = -position
                    positions.append(position)
            yield positions

    @thread_worker
    def grab_property_value(self, device: object, property_name: str, widget) -> Iterator:
        """Grab value of property and yield
        :param device: device to grab property from
        :param property_name: name of property to get
        :param widget: corresponding device widget
        :return: value of property and widget to update.
        """
        while True:  # best way to do this or have some sort of break?
            time.sleep(1.0)
            value = getattr(device, property_name)
            yield value, widget

    def create_operation_widgets(self, device_name: str, operation_name: str, operation_specs: dict) -> None:
        """Create widgets for operation specifications."""
        device = getattr(self.instrument, f'{operation_name}s')[device_name]
        # Note: scan_for_properties only takes device parameter
        # The properties and methods filters would need to be applied after scanning
        widgets = scan_for_properties(device)
        getattr(self, f'{operation_name}_widgets')[device_name] = widgets

    def update_acquisition_layer(self, image: np.ndarray, camera_name: str) -> None:
        """Update the acquisition image layer in the viewer.

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

            layer_name = 'acquisition'
            if layer_name in self.instrument_view.viewer.layers:
                layer = self.instrument_view.viewer.layers[layer_name]
                layer.data = image
                layer.scale = np.array([pixel_size_um, pixel_size_um])
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

    @thread_worker
    def grab_writer_property(self, device: object, property_name: str, widget) -> Iterator:
        """Grab writer property values."""
        while True:
            time.sleep(1.0)
            value = getattr(device, property_name)
            yield value, widget

    def update_property_value(self, value, widget) -> None:
        """Update property widget value."""
        if hasattr(widget, 'setValue'):
            widget.setValue(value)
        elif hasattr(widget, 'setText'):
            widget.setText(str(value))

    @Slot(str)
    def update_writer_property_value(self, property_name: str) -> None:
        """Update writer property value from widget."""
        # Implementation would depend on specific requirements

    def create_tile_list(self) -> list:
        """Create list of tiles for acquisition."""
        tiles = []
        # Get channels from the channel plan widget's channels attribute
        channels = getattr(self.channel_plan, 'channels', [])

        # Get tile positions from volume plan - need to check what attribute exists
        # This is a placeholder implementation that needs to be updated based on actual API
        tile_positions = []  # Would need to get actual positions from volume_plan

        for channel in channels:
            for tile_position in tile_positions:
                tiles.append(self.write_tile(channel, tile_position))
        return tiles

    def write_tile(self, channel: str, tile) -> dict:
        """Write tile configuration."""
        return {
            'channel': channel,
            'position': tile,
            'metadata': {
                'timestamp': datetime.now().isoformat(),
            },
        }

    def update_config_on_quit(self) -> None:
        """Update configuration when application quits."""
        reply = self.update_config_query()
        if reply == QMessageBox.StandardButton.Yes:
            # Save current configuration
            pass

    def update_config_query(self) -> int:
        """Query user about updating configuration."""
        msgBox = QMessageBox()
        msgBox.setText('Configuration has been modified.')
        msgBox.setInformativeText('Do you want to save your changes?')
        msgBox.setStandardButtons(
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        msgBox.setDefaultButton(QMessageBox.StandardButton.Save)
        return msgBox.exec()

    def select_directory(self, pressed: bool, msgBox: QMessageBox) -> None:
        """Select directory for saving files."""
        directory = QFileDialog.getExistingDirectory(self, 'Select Directory')
        if directory:
            msgBox.accept()

    def close(self) -> bool:
        """Close the acquisition view."""
        self.update_config_on_quit()
        return super().close()

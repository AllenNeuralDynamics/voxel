from PySide6.QtWidgets import (
    QTabWidget,
    QTabBar,
    QWidget,
    QPushButton,
    QMenu,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QSpinBox,
)
from PySide6.QtGui import QAction
from vidgets.miscellaneous_widgets.q_item_delegates import (
    QSpinItemDelegate,
    QTextItemDelegate,
    QComboItemDelegate,
)
from vidgets.miscellaneous_widgets.q_scrollable_line_edit import QScrollableLineEdit
from vidgets.base_device_widget import label_maker
import numpy as np
from PySide6.QtCore import Signal, Qt
from inflection import singularize
from math import isnan
import pint
import inspect


class ChannelPlanWidget(QTabWidget):
    """Widget defining parameters per tile per channel"""

    channelAdded = Signal(str)
    channelChanged = Signal()

    def __init__(self, instrument_view, channels: dict, properties: dict, unit: str = "um"):
        """
        :param instrument_view: view associated with instrument
        :param channels: dictionary defining channels for instrument
        :param properties: allowed prop for devices
        :param unit: unit of all values
        """

        super().__init__()

        self.possible_channels = channels
        self.channels = []
        self.properties = properties
        self.default_prefix = properties.get("default_prefix", "")
        self.default_step_size = properties.get("default_step_size", 0.0)
        self.column_data_types = {"step size [um]": float, "steps": int, "prefix": str}

        # setup units for step size and step calculation
        unit_registry = pint.UnitRegistry()
        self.unit = getattr(unit_registry, unit)  # TODO: How to check if unit is in pint?
        self.micron = unit_registry.um

        self.steps = {}  # dictionary of number of steps for each tile in each channel
        self.step_size = {}  # dictionary of step size for each tile in each channel
        self.prefix = {}  # dictionary of prefix for each tile in each channel

        self._tile_volumes = np.zeros([1, 1], dtype=float)  # array of tile starts and ends. Constant for every channel

        self.tab_bar = ChannelPlanTabBar()
        self.tab_bar.setMovable(True)
        self.setTabBar(self.tab_bar)

        self.channel_order = QComboBox()
        self.channel_order.addItems(
            [
                "per Tile",
                "per Volume",
            ]
        )
        self.setCornerWidget(self.channel_order)
        self.mode = self.channel_order.currentText()
        self.channel_order.currentTextChanged.connect(lambda value: setattr(self, "mode", value))

        # initialize column dictionaries and column delgates
        self.initialize_tables(instrument_view)

        # add tab with button to add channels
        self.add_tool = QToolButton()
        self.add_tool.setText("+")
        menu = QMenu()
        for channel in self.possible_channels:
            action = QAction(str(channel), self)
            action.triggered.connect(lambda clicked, ch=channel: self.add_channel(ch))
            menu.addAction(action)
        self.add_tool.setMenu(menu)
        self.add_tool.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.insertTab(0, QWidget(), "")  # insert dummy qwidget
        self.tab_bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, self.add_tool)

        # reorder channels if tabbar moved
        self.tab_bar.tabMoved.connect(
            lambda: setattr(self, "channels", [self.tabText(ch) for ch in range(self.count() - 1)])
        )
        self._apply_all = True  # external flag to dictate behaviour of added tab

    def initialize_tables(self, instrument_view) -> None:
        """
        Initialize table for all channels with proper columns and delegates
        :param instrument_view: view object that contains all widget for devices in an instrument
        """

        # TODO: Checks here if prop or device isn't part of the instrument? Or go in instrument validation?

        for channel in self.possible_channels:
            setattr(self, f"{channel}_table", QTableWidget())
            table = getattr(self, f"{channel}_table")
            table.cellChanged.connect(self.cell_edited)

            columns = ["step size [um]", "steps", "prefix"]
            delegates = [QSpinItemDelegate(), QSpinItemDelegate(minimum=0, step=1), QTextItemDelegate()]
            for device_type, properties in self.properties.items():
                if device_type in self.possible_channels[channel]:
                    for device_name in self.possible_channels[channel][device_type]:
                        device_widget = getattr(instrument_view, f"{singularize(device_type)}_widgets")[device_name]
                        device_object = getattr(instrument_view.instrument, device_type)[device_name]
                        for prop in properties:
                            # select delegate to use based on type
                            column_name = label_maker(f"{device_name}_{prop}")
                            descriptor = getattr(type(device_object), prop)
                            if not isinstance(descriptor, property) or getattr(descriptor, "fset", None) is None:
                                self.column_data_types[column_name] = str  # default to str instead of None
                                continue
                            # try and correctly type properties based on setter
                            fset = getattr(descriptor, "fset")
                            input_type = list(inspect.signature(fset).parameters.values())[-1].annotation
                            self.column_data_types[column_name] = input_type if input_type != inspect._empty else str
                            setattr(self, column_name, {})
                            columns.append(column_name)
                            prop_widget = getattr(device_widget, f"{prop}_widget")
                            if type(prop_widget) in [QScrollableLineEdit, QSpinBox]:
                                minimum = getattr(descriptor, "minimum", float("-inf"))
                                maximum = getattr(descriptor, "maximum", float("inf"))
                                step = getattr(descriptor, "step", 0.1)
                                delegates.append(QSpinItemDelegate(minimum=minimum, maximum=maximum, step=step))
                                setattr(self, column_name + "_value_function", prop_widget.value)
                            elif isinstance(getattr(device_widget, f"{prop}_widget"), QComboBox):
                                widget = getattr(device_widget, f"{prop}_widget")
                                items = [widget.itemText(i) for i in range(widget.count())]
                                delegates.append(QComboItemDelegate(items=items))  # type: ignore
                                setattr(self, column_name + "_value_function", prop_widget.currentText)
                            else:  # TODO: How to handle dictionary values
                                delegates.append(QTextItemDelegate())
                                setattr(self, column_name + "_value_function", prop_widget.text)
                elif dict in type(properties).__mro__:  # TODO: how to validate the GUI yaml?
                    column_name = label_maker(device_type)
                    setattr(self, column_name, {})
                    setattr(self, column_name + "_initial_value", properties.get("initial_value", None))
                    columns.append(column_name)
                    if properties["delegate"] == "spin":
                        minimum = properties.get("minimum", None)
                        maximum = properties.get("maximum", None)
                        step = properties.get("step", 0.1 if properties["type"] == "float" else 1)
                        delegates.append(QSpinItemDelegate(minimum=minimum, maximum=maximum, step=step))
                        self.column_data_types[column_name] = float if properties["type"] == "float" else int
                    elif properties["delegate"] == "combo":
                        items = properties["items"]
                        delegates.append(QComboItemDelegate(items=items))  # type: ignore
                        type_mapping = {"int": int, "float": float, "str": str}
                        self.column_data_types[column_name] = type_mapping[properties["type"]]
                    else:
                        delegates.append(QTextItemDelegate())
                        self.column_data_types[column_name] = str

            columns.append("row, column")

            for i, delegate in enumerate(delegates):
                # table does not take ownership of the delegates, so they are removed from memory as they
                # are local variables causing a Segmentation fault. Need to be attributes
                setattr(self, f"{columns[i]}_{channel}_delegate", delegate)
                table.setItemDelegateForColumn(i, delegate)
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels(columns)
            table.resizeColumnsToContents()
            table.setColumnHidden(len(columns) - 1, True)  # hide row, column since it will only be used internally

            table.verticalHeader().hide()

    @property
    def apply_all(self) -> bool:
        """Property for the state of apply all
        :return: boolean indicating if settings for the 0,0 tile are applied to all tiles"""
        return self._apply_all

    @apply_all.setter
    def apply_all(self, value: bool) -> None:
        """When apply all is toggled, update existing channels"""

        if self._apply_all != value:
            for channel in self.channels:
                table = getattr(self, f"{channel}_table")

                for i in range(1, table.rowCount()):  # skip first row
                    for j in range(table.columnCount() - 1):  # skip last column
                        item = table.item(i, j)
                        self.enable_item(item, not value)
                        if value:
                            item.setData(Qt.ItemDataRole.EditRole, table.item(0, j).data(Qt.ItemDataRole.EditRole))
        self._apply_all = value

    @property
    def tile_volumes(self) -> np.ndarray:
        """
        Property of tile volumes in 2d numpy array
        :return: 2d numpy array containing the volume of the tile at the i, j location
        """
        return self._tile_volumes

    @tile_volumes.setter
    def tile_volumes(self, value: np.ndarray) -> None:
        """When tile dims is updated, update size of channel arrays"""

        self._tile_volumes = value
        for channel in self.channels:
            table = getattr(self, f"{channel}_table")
            for i in range(table.columnCount() - 1):  # skip row, column
                header = table.horizontalHeaderItem(i).text()
                if header == "step size [um]":
                    getattr(self, "step_size")[channel] = np.resize(getattr(self, "step_size")[channel], value.shape)
                else:
                    getattr(self, header)[channel] = np.resize(getattr(self, header)[channel], value.shape)
            self.step_size[channel] = np.resize(self.step_size[channel], value.shape)
            self.steps[channel] = np.resize(self.steps[channel], value.shape)
            self.prefix[channel] = np.resize(self.prefix[channel], value.shape)
            self._tile_volumes = value
            for row in range(table.rowCount()):
                tile_index = [int(x) for x in table.item(row, table.columnCount() - 1).text() if x.isdigit()]
                if tile_index[0] < value.shape[0] and tile_index[1] < value.shape[1]:
                    self.update_steps(tile_index, row, channel)

    def enable_item(self, item: QTableWidgetItem, enable: bool) -> None:
        """
        Change flags for enabling/disabling items in channel_plan table
        :param item: item to change flag for
        :param enable: boolean value indicating if flags should be configured to enable or disable item
        """

        flags = QTableWidgetItem().flags()
        if not enable:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        else:
            flags |= Qt.ItemFlag.ItemIsEditable
            flags |= Qt.ItemFlag.ItemIsEnabled
            flags |= Qt.ItemFlag.ItemIsSelectable
        item.setFlags(flags)

    def add_channel(self, channel: str) -> None:
        """Add channel to acquisition
        :param channel: name of channel to add
        """

        table = getattr(self, f"{channel}_table")

        for i in range(3, table.columnCount() - 1):  # skip steps, step_size, prefix, row/col
            column_name = table.horizontalHeaderItem(i).text()
            delegate = getattr(self, f"{column_name}_{channel}_delegate", None)
            if delegate is not None:  # Skip if prop did not have setter
                array = getattr(self, f"{column_name}")
                if isinstance(delegate, QSpinItemDelegate):
                    array[channel] = np.zeros(self._tile_volumes.shape)
                elif isinstance(delegate, QComboItemDelegate):
                    array[channel] = np.empty(self._tile_volumes.shape, dtype="U100")
                else:
                    array[channel] = np.empty(self._tile_volumes.shape, dtype="U100")

                if getattr(self, column_name + "_initial_value", None) is not None:  # get initial value
                    array[channel][:, :] = getattr(self, column_name + "_initial_value")
                elif getattr(self, column_name + "_value_function", None) is not None:
                    # call value function to get current set point
                    array[channel][:, :] = getattr(self, column_name + "_value_function")()

        self.steps[channel] = np.zeros(self._tile_volumes.shape, dtype=int)
        self.step_size[channel] = np.zeros(self._tile_volumes.shape, dtype=float)
        self.step_size[channel][:, :] = self.default_step_size
        self.prefix[channel] = np.zeros(self._tile_volumes.shape, dtype="U100")
        self.prefix[channel][:, :] = self.default_prefix

        self.insertTab(0, table, channel)
        self.setCurrentIndex(0)

        # add button to remove channel
        button = QPushButton("x")
        button.setMaximumWidth(20)
        button.setMaximumHeight(20)
        button.pressed.connect(lambda: self.remove_channel(channel))
        self.tab_bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, button)

        # remove channel from add_tool menu
        menu = self.add_tool.menu()
        if menu is not None:
            for action in menu.actions():
                if action.text() == channel:
                    menu.removeAction(action)
        self.add_tool.setMenu(menu)

        self.channels = [channel] + self.channels

        self.channelAdded.emit(channel)

    def add_channel_rows(self, channel: str, order: list) -> None:
        """Add rows to channel table in specific order of tiles
        :param channel: name of channel
        :param order: list of tile order e.g. [[0,0], [0,1]]
        """

        table = getattr(self, f"{channel}_table")
        table.blockSignals(True)
        table.clearContents()
        table.setRowCount(0)

        arrays = [self.step_size[channel]]
        delegates = [getattr(self, f"step size [um]_{channel}_delegate")]
        # iterate through columns to find relevant arrays to update
        for i in range(1, table.columnCount() - 1):  # skip row, column
            arrays.append(getattr(self, table.horizontalHeaderItem(i).text())[channel])
            delegates.append(getattr(self, f"{table.horizontalHeaderItem(i).text()}_{channel}_delegate"))
        for tile in order:
            table_row = table.rowCount()
            table.insertRow(table_row)
            item = QTableWidgetItem(str(tile))
            table.setItem(table_row, table.columnCount() - 1, item)
            for column, array in enumerate(arrays):
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)  # change the alignment
                if isinstance(delegates[column], QSpinItemDelegate):
                    item.setData(Qt.ItemDataRole.EditRole, float(array[*tile]))
                else:
                    item.setData(Qt.ItemDataRole.EditRole, str(array[*tile]))
                table.setItem(table_row, column, item)
                if table_row != 0:  # first row/tile always enabled
                    self.enable_item(item, not self.apply_all)
        table.blockSignals(False)

    def remove_channel(self, channel: str) -> None:
        """Remove channel from acquisition
        :param channel: name of channel
        """

        self.channels.remove(channel)

        table = getattr(self, f"{channel}_table")
        index = self.indexOf(table)

        self.removeTab(index)

        # remove key from attributes
        for i in range(table.columnCount() - 1):  # skip row, column
            header = table.horizontalHeaderItem(i).text()
            if header == "step size [um]":
                del getattr(self, "step_size")[channel]
            else:
                del getattr(self, header)[channel]

        # add channel back to add_tool
        menu = self.add_tool.menu()
        if menu is not None:
            action = QAction(channel, self)
            action.triggered.connect(lambda clicked, ch=channel: self.add_channel(ch))
            menu.addAction(action)
            self.add_tool.setMenu(menu)

        self.channelChanged.emit()

    def cell_edited(self, row: int, column: int, channel: str | None = None) -> None:
        """
        Update table based on cell edit
        :param row: row of item edited
        :param column: column of item edited
        :param channel: channel name of item edited
        """

        channel = self.tabText(self.currentIndex()) if channel is None else channel
        table = getattr(self, f"{channel}_table")

        table.blockSignals(True)  # block signals so updating cells doesn't trigger cell edit again
        tile_index = [int(x) for x in table.item(row, table.columnCount() - 1).text() if x.isdigit()]

        step_size = 0.0  # Initialize default values
        steps = 0

        if column in [0, 1]:
            step_size, steps = (
                self.update_steps(tile_index, row, channel)
                if column == 0
                else self.update_steps(tile_index, row, channel)
            )
            table.item(row, 0).setData(Qt.ItemDataRole.EditRole, step_size)
            table.item(row, 1).setData(Qt.ItemDataRole.EditRole, steps)

        # FIXME: I think this is would be considered unexpected behavior
        array = getattr(self, table.horizontalHeaderItem(column).text(), self.step_size)[channel]
        value = table.item(row, column).data(Qt.ItemDataRole.EditRole)
        if self.apply_all:
            array[:, :] = value
            for i in range(1, table.rowCount()):
                item_0 = table.item(0, column)
                table.item(i, column).setData(Qt.ItemDataRole.EditRole, item_0.data(Qt.ItemDataRole.EditRole))
                if column == 0:  # update steps as well
                    table.item(i, column + 1).setData(Qt.ItemDataRole.EditRole, int(steps))
                elif column == 1:  # update step_size as well
                    table.item(i, column - 1).setData(Qt.ItemDataRole.EditRole, float(step_size))
        else:
            array[*tile_index] = value
        table.blockSignals(False)
        self.channelChanged.emit()

    def update_steps(self, tile_index: list[int], row: int, channel: str) -> tuple[float, int]:
        """
        Update number of steps based on volume
        :param tile_index: integer list specifying row, column value of tile
        :param row: row of item that correspond to tile at position tile_index
        :param channel: name of channel
        :return: step_size in um and number of steps
        """

        volume_um = (self.tile_volumes[*tile_index] * self.unit).to(self.micron)
        index = tile_index if not self.apply_all else [slice(None), slice(None)]
        steps = volume_um / (
            float(getattr(self, f"{channel}_table").item(row, 0).data(Qt.ItemDataRole.EditRole)) * self.micron
        )
        if steps != 0 and not isnan(steps) and steps not in [float("inf"), float("-inf")]:
            step_size = float(
                round(volume_um / steps, 4) / self.micron
            )  # make dimensionless again for simplicity in code
            steps = int(round(steps))
        else:
            steps = 0
            step_size = 0
        self.steps[channel][*index] = steps

        return step_size, steps

    def update_step_size(self, tile_index: list[int], row: int, channel: str) -> tuple[float, int]:
        """
        Update number of steps based on volume
        :param tile_index: integer list specifying row, column value of tile
        :param row: row of item that correspond to tile at position tile_index
        :param channel: name of channel
        :return: step_size in um and number of steps
        """

        volume_um = (self.tile_volumes[*tile_index] * self.unit).to(self.micron)
        index = tile_index if not self.apply_all else [slice(None), slice(None)]
        # make dimensionless again for simplicity in code
        step_size = (
            volume_um / float(getattr(self, f"{channel}_table").item(row, 1).data(Qt.ItemDataRole.EditRole))
        ) / self.micron
        if step_size != 0 and not isnan(step_size) and step_size not in [float("inf"), float("-inf")]:
            steps = int(round(volume_um / (step_size * self.micron)))
            step_size = float(round(step_size, 4))
        else:
            steps = 0
            step_size = 0
        self.step_size[channel][*index] = step_size
        return step_size, steps


class ChannelPlanTabBar(QTabBar):
    """TabBar that will keep add channel tab at end"""

    def __init__(self):
        super(ChannelPlanTabBar, self).__init__()
        self.tabMoved.connect(self.tab_index_check)

    def tab_index_check(self, prev_index: int, curr_index: int) -> None:
        """
        Keep last tab as last tab
        :param prev_index: previous index of tab
        :param curr_index: index tab was moved to
        """

        if prev_index == self.count() - 1:
            self.moveTab(curr_index, prev_index)

    def mouseMoveEvent(self, a0) -> None:
        """
        Make last tab immovable
        :param a0: qmouseevent that triggered call
        :return:
        """
        index = self.currentIndex()
        if index == self.count() - 1:  # last tab is immovable
            return
        super().mouseMoveEvent(a0)

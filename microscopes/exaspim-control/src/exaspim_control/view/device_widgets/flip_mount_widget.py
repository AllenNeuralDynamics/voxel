from PySide6.QtWidgets import QSizePolicy

from exaspim_control.view.base_device_widget import BaseDeviceWidget, create_widget
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exaspim_control.voxel_classic.devices.flip_mount.base import BaseFlipMount


class FlipMountWidget(BaseDeviceWidget):
    """Widget for handling flip mount properties and controls."""

    def __init__(self, flip_mount: 'BaseFlipMount'):
        """
        Initialize the FlipMountWidget object.

        :param flip_mount: Flip mount object
        :type flip_mount: object
        """
        self._flip_mount = flip_mount
        self._display_properties = {'position': self._flip_mount.position}
        super().__init__(
            device_type=type(flip_mount),
            properties=self._display_properties,
            updating_props=list(
                self._display_properties.keys(),
            ),
        )
        self.attach_device(self._flip_mount)

        positions = self.property_widgets['position'].layout().itemAt(1).widget()
        positions.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        flip_time = self.property_widgets['flip_time_ms'].layout().itemAt(1).widget()
        flip_time.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        central_widget = self.centralWidget()
        if central_widget is not None and central_widget.layout() is not None:
            central_widget.layout().setSpacing(0)  # type: ignore
        self.setCentralWidget(
            create_widget('H', self.property_widgets['position'], self.property_widgets['flip_time_ms'])
        )

from qtpy.QtWidgets import QSizePolicy

from view.widgets.base_device_widget import BaseDeviceWidget, create_widget, scan_for_properties


class FlipMountWidget(BaseDeviceWidget):
    """Widget for handling flip mount properties and controls."""

    def __init__(self, flip_mount: object):
        """
        Initialize the FlipMountWidget object.

        :param flip_mount: Flip mount object
        :type flip_mount: object
        """
        self.flip_mount_properties = scan_for_properties(flip_mount)
        super().__init__(type(flip_mount), self.flip_mount_properties)

        positions = self.property_widgets["position"].layout().itemAt(1).widget()
        positions.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        flip_time = self.property_widgets["flip_time_ms"].layout().itemAt(1).widget()
        flip_time.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        central_widget = self.centralWidget()
        central_widget.layout().setSpacing(0)  # remove space between central widget and newly formatted widgets
        self.setCentralWidget(
            create_widget("H", self.property_widgets["position"], self.property_widgets["flip_time_ms"])
        )

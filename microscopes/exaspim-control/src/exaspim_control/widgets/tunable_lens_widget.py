from qtpy.QtWidgets import QSizePolicy

from view.widgets.base_device_widget import BaseDeviceWidget, create_widget, scan_for_properties


class TunableLensWidget(BaseDeviceWidget):
    """Widget for handling tunable lens properties and controls."""

    def __init__(self, tunable_lens: object):
        """
        Initialize the TunableLensWidget object.

        :param tunable_lens: Tunable lens object
        :type tunable_lens: object
        """
        self.tunable_lens_properties = scan_for_properties(tunable_lens)
        super().__init__(type(tunable_lens), self.tunable_lens_properties)

        modes = self.property_widgets["mode"].layout().itemAt(1).widget()
        modes.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        temperature = self.property_widgets["temperature_c"].layout().itemAt(1).widget()
        temperature.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        central_widget = self.centralWidget()
        central_widget.layout().setSpacing(0)  # remove space between central widget and newly formatted widgets
        self.setCentralWidget(create_widget("H", self.property_widgets["mode"], self.property_widgets["temperature_c"]))

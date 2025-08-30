from PySide6.QtWidgets import QSizePolicy

from exaspim_control.view.base_device_widget import BaseDeviceWidget, create_widget, scan_for_properties


class TunableLensWidget(BaseDeviceWidget):
    """Widget for handling tunable lens properties and controls."""

    def __init__(self, tunable_lens: object):
        """
        Initialize the TunableLensWidget object.

        :param tunable_lens: Tunable lens object
        :type tunable_lens: object
        """
        self.tunable_lens_properties = scan_for_properties(tunable_lens)
        super().__init__(type(tunable_lens), properties=self.tunable_lens_properties, updating_props=None)

        modes = self.property_widgets['mode'].layout().itemAt(1).widget()
        modes.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        temperature = self.property_widgets['temperature_c'].layout().itemAt(1).widget()
        temperature.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        central_widget = self.centralWidget()
        if central_widget is not None and central_widget.layout() is not None:
            central_widget.layout().setSpacing(0)  # type: ignore
        self.setCentralWidget(create_widget('H', self.property_widgets['mode'], self.property_widgets['temperature_c']))

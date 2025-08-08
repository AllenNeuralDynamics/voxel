import importlib

from qtpy.QtGui import QDoubleValidator, QIntValidator
from qtpy.QtWidgets import QLabel

from view.widgets.base_device_widget import BaseDeviceWidget, scan_for_properties
from view.widgets.miscellaneous_widgets.q_scrollable_line_edit import QScrollableLineEdit


class StageWidget(BaseDeviceWidget):
    """Widget for handling stage properties and controls."""

    def __init__(self, stage: object, advanced_user: bool = True):
        """
        Initialize the StageWidget object.

        :param stage: Stage object
        :type stage: object
        :param advanced_user: Whether the user is advanced, defaults to True
        :type advanced_user: bool, optional
        """
        self.stage_properties = scan_for_properties(stage) if advanced_user else {"position_mm": stage.position_mm}

        self.stage_module = importlib.import_module(stage.__module__)
        super().__init__(type(stage), self.stage_properties)

        # alter position_mm widget to use instrument_axis as label
        self.property_widgets["position_mm"].setEnabled(False)
        position_label = self.property_widgets["position_mm"].findChild(QLabel)
        # TODO: Change when deliminated property is updated
        unit = getattr(type(stage).position_mm, "unit", "mm")
        # TODO: Change and add rotation stage to voxel devices
        if stage.instrument_axis in ["t", "r"]:  # rotation stages
            unit = "°"
        position_label.setText(f"{stage.instrument_axis} [{unit}]")

        # update property_widgets['position_mm'] text to be white
        style = """
        QScrollableLineEdit {
            color: white;
        }

        QLabel {
            color : white;
        }
        """
        self.property_widgets["position_mm"].setStyleSheet(style)

    def create_text_box(self, name: str, value: object) -> QScrollableLineEdit:
        """
        Create a text box for the given property.

        :param name: Property name
        :type name: str
        :param value: Property value
        :type value: object
        :return: Text box widget
        :rtype: QScrollableLineEdit
        """
        value_type = type(value)
        textbox = QScrollableLineEdit(str(value))
        textbox.editingFinished.connect(lambda: self.textbox_edited(name))
        if float in value_type.__mro__:
            validator = QDoubleValidator()
            validator.setNotation(QDoubleValidator.StandardNotation)
            validator.setDecimals(3)
            textbox.setValidator(validator)
            textbox.setValue(round(value, 3))
        elif int in value_type.__mro__:
            validator = QIntValidator()
            textbox.setValidator(validator)
        return textbox

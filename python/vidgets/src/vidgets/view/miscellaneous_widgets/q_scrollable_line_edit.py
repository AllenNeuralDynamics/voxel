from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QIntValidator, QDoubleValidator
import typing


class QScrollableLineEdit(QLineEdit):
    """Widget inheriting from QLineEdit that allows value to be scrollable"""

    def wheelEvent(self, a0):
        super().wheelEvent(a0)
        if self.validator() is not None and isinstance(self.validator(), (QIntValidator, QDoubleValidator)):
            if isinstance(self.validator(), QDoubleValidator):
                dec = len(self.text()[self.text().index(".") + 1 :]) if "." in self.text() else 0
                change = 10 ** (-dec) if a0.angleDelta().y() > 0 else -(10 ** (-dec))
                new_value = float(f"%.{dec}f" % float(float(self.text()) + change))
            else:  # QIntValidator
                new_value = int(self.text()) + 1 if a0.angleDelta().y() > 0 else int(self.text()) - 1
            # Use type assertions since we've checked the validator types
            validator = typing.cast("typing.Union[QIntValidator, QDoubleValidator]", self.validator())
            if validator.bottom() <= new_value <= validator.top():
                self.setText(str(new_value))
                self.editingFinished.emit()

    def value(self):
        """Get float or integer of text"""
        return float(self.text())

    def setValue(self, value):
        """Set number as text"""
        self.setText(str(value))

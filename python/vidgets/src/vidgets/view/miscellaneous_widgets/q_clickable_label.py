from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Signal
from PySide6.QtGui import QMouseEvent


class QClickableLabel(QLabel):
    """QLabel that emits signal when clicked"""

    clicked = Signal()

    def mousePressEvent(self, ev: QMouseEvent, **kwargs) -> None:
        """
        Overwriting to emit signal
        :param ev: mouse click event
        """
        self.clicked.emit()
        super().mousePressEvent(ev, **kwargs)

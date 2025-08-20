from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSlider


class QScrollableFloatSlider(QSlider):
    """QSlider that will emit signal if scrolled with mouse wheel and allow float values"""

    sliderMoved = Signal(float)  # redefine slider move to emit float

    def __init__(self, decimals=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.divisor = 10**decimals

    def value(self):
        return float(super().value()) / self.divisor

    def setMinimum(self, a0):
        return super().setMinimum(int(a0 * self.divisor))

    def setMaximum(self, a0):
        return super().setMaximum(int(a0 * self.divisor))

    def maximum(self):
        return super().maximum() / self.divisor

    def minimum(self):
        return super().minimum() / self.divisor

    def setSingleStep(self, a0):
        return super().setSingleStep(a0 * self.divisor)

    def singleStep(self):
        return float(super().singleStep()) / self.divisor

    def setValue(self, a0):
        super().setValue(int(a0 * self.divisor))

    def wheelEvent(self, e):
        super().wheelEvent(e)
        value = self.value()
        self.sliderMoved.emit(value)
        self.sliderReleased.emit()

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if ev.buttons() == Qt.MouseButton.LeftButton:
            value = self.value()
            self.sliderMoved.emit(value)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        value = self.value()
        self.sliderMoved.emit(value)

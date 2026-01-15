"""Number input primitives."""

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QWidget


class SpinBox(QSpinBox):
    """A styled integer spinbox.

    Usage:
        SpinBox()
        SpinBox(value=10, min=0, max=100)
        SpinBox(value=5, min=1, max=10, step=1)
    """

    def __init__(
        self,
        value: int = 0,
        min: int | None = None,
        max: int | None = None,
        step: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        if min is not None and max is not None:
            self.setRange(min, max)
        elif min is not None:
            self.setMinimum(min)
        elif max is not None:
            self.setMaximum(max)
        if step is not None:
            self.setSingleStep(step)
        if value:
            self.setValue(value)


class DoubleSpinBox(QDoubleSpinBox):
    """A styled double spinbox.

    Usage:
        DoubleSpinBox()
        DoubleSpinBox(value=1.5, min=0.0, max=10.0)
        DoubleSpinBox(value=1.33, min=1.0, max=2.0, decimals=3, step=0.01)
    """

    def __init__(
        self,
        value: float = 0.0,
        min: float | None = None,
        max: float | None = None,
        decimals: int | None = None,
        step: float | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        if decimals is not None:
            self.setDecimals(decimals)
        if min is not None and max is not None:
            self.setRange(min, max)
        elif min is not None:
            self.setMinimum(min)
        elif max is not None:
            self.setMaximum(max)
        if step is not None:
            self.setSingleStep(step)
        if value:
            self.setValue(value)

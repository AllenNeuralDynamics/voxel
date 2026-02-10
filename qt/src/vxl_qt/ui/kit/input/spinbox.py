"""Number input primitives."""

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QWidget

from vxl_qt.ui.kit.theme import Colors, ControlSize


def _spinbox_style(size: ControlSize = ControlSize.MD) -> str:
    """Return minimal spinbox styling for dark theme."""
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.BG_LIGHT};
            color: {Colors.TEXT};
            border: 1px solid {Colors.BORDER};
            border-radius: {size.radius}px;
            font-size: {size.font}px;
            padding: 0 {size.px}px;
        }}
        QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {Colors.BORDER_FOCUS};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {Colors.ACCENT};
        }}
        QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {Colors.BG_MEDIUM};
            color: {Colors.TEXT_DISABLED};
        }}
    """


class SpinBox(QSpinBox):
    """A styled integer spinbox.

    Usage:
        SpinBox()
        SpinBox(value=10, min=0, max=100)
        SpinBox(value=5, min=1, max=10, step=1, size=ControlSize.LG)
    """

    def __init__(
        self,
        value: int = 0,
        min_val: int | None = None,
        max_val: int | None = None,
        step: int | None = None,
        size: ControlSize = ControlSize.MD,
        keyboard_tracking: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setKeyboardTracking(keyboard_tracking)
        if min_val is not None and max_val is not None:
            self.setRange(min_val, max_val)
        elif min_val is not None:
            self.setMinimum(min_val)
        elif max_val is not None:
            self.setMaximum(max_val)
        if step is not None:
            self.setSingleStep(step)
        if value:
            self.setValue(value)
        self.setFixedHeight(size.h)
        self.setStyleSheet(_spinbox_style(size))


class DoubleSpinBox(QDoubleSpinBox):
    """A styled double spinbox.

    Usage:
        DoubleSpinBox()
        DoubleSpinBox(value=1.5, min=0.0, max=10.0)
        DoubleSpinBox(value=1.33, min=1.0, max=2.0, decimals=3, step=0.01, size=ControlSize.LG)
    """

    def __init__(
        self,
        value: float = 0.0,
        min_val: float | None = None,
        max_val: float | None = None,
        decimals: int | None = None,
        step: float | None = None,
        size: ControlSize = ControlSize.MD,
        keyboard_tracking: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setKeyboardTracking(keyboard_tracking)
        if decimals is not None:
            self.setDecimals(decimals)
        if min_val is not None and max_val is not None:
            self.setRange(min_val, max_val)
        elif min_val is not None:
            self.setMinimum(min_val)
        elif max_val is not None:
            self.setMaximum(max_val)
        if step is not None:
            self.setSingleStep(step)
        if value:
            self.setValue(value)
        self.setFixedHeight(size.h)
        self.setStyleSheet(_spinbox_style(size))

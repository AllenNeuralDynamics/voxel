"""Number input primitives."""

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QWidget

from spim_qt.ui.primitives.utils import icon_data_uri
from spim_qt.ui.theme import BorderRadius, Colors, FontSize, Size, Spacing


def _spinbox_style() -> str:
    """Return consistent spinbox styling."""
    up_icon = icon_data_uri("mdi.chevron-up", Colors.TEXT_MUTED, Size.ICON_SM)
    down_icon = icon_data_uri("mdi.chevron-down", Colors.TEXT_MUTED, Size.ICON_SM)
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.BG_LIGHT};
            border: 1px solid {Colors.BORDER};
            border-radius: {BorderRadius.SM}px;
            padding: {Spacing.XS}px {Spacing.MD}px;
            padding-right: 18px;
            color: {Colors.TEXT};
            font-size: {FontSize.SM}px;
            min-height: {Size.INPUT_HEIGHT}px;
            max-height: {Size.INPUT_HEIGHT}px;
        }}
        QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {Colors.BORDER_FOCUS};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {Colors.ACCENT};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 16px;
            border: none;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 16px;
            border: none;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: {up_icon};
            width: {Size.ICON_SM}px;
            height: {Size.ICON_SM}px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: {down_icon};
            width: {Size.ICON_SM}px;
            height: {Size.ICON_SM}px;
        }}
        QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {Colors.BG_MEDIUM};
            color: {Colors.TEXT_DISABLED};
            border-color: {Colors.BORDER};
        }}
    """


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
        self.setStyleSheet(_spinbox_style())


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
        self.setStyleSheet(_spinbox_style())

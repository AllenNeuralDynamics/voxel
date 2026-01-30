"""Text input widget with consistent styling."""

from PySide6.QtWidgets import QLineEdit, QWidget

from vxl_qt.ui.kit.theme import Colors, ControlSize


class TextInput(QLineEdit):
    """Styled text input field.

    A QLineEdit with consistent visual styling matching the kit theme.

    Usage:
        TextInput(placeholder="Enter name...")
        TextInput(placeholder="Search...", size=ControlSize.SM)
        TextInput(text="initial value", size=ControlSize.LG)
    """

    def __init__(
        self,
        text: str = "",
        placeholder: str = "",
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)

        if placeholder:
            self.setPlaceholderText(placeholder)

        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG_LIGHT};
                border: 1px solid {Colors.BORDER};
                border-radius: {size.radius}px;
                height: {size.h}px;
                padding: 0 {size.px}px;
                color: {Colors.TEXT};
                font-size: {size.font}px;
            }}
            QLineEdit:hover {{
                border-color: {Colors.BORDER_FOCUS};
            }}
            QLineEdit:focus {{
                border-color: {Colors.ACCENT};
            }}
            QLineEdit::placeholder {{
                color: {Colors.TEXT_DISABLED};
            }}
        """)

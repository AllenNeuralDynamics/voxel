"""Button components with consistent styling."""

from typing import Literal

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from voxel_qt.ui.theme import BorderRadius, Colors, FontSize, Size, Spacing

ButtonVariant = Literal["primary", "secondary", "success", "danger", "ghost"]


class Button(QPushButton):
    """A styled button component with consistent appearance.

    Supports multiple visual variants for different contexts.

    Usage:
        btn = Button("Click Me")
        btn = Button("Submit", variant="primary")
        btn = Button("Cancel", variant="secondary")
        btn = Button("Halt", variant="danger")
    """

    def __init__(
        self,
        text: str = "",
        variant: ButtonVariant = "secondary",
        icon: QIcon | None = None,
        checkable: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._variant = variant

        if icon is not None:
            self.setIcon(icon)

        if checkable:
            self.setCheckable(True)

        self._apply_style()

    def _apply_style(self) -> None:
        """Apply styling based on variant."""
        styles = {
            "primary": self._primary_style,
            "secondary": self._secondary_style,
            "success": self._success_style,
            "danger": self._danger_style,
            "ghost": self._ghost_style,
        }
        style_fn = styles.get(self._variant, self._secondary_style)
        self.setStyleSheet(style_fn())

    def _secondary_style(self) -> str:
        """Secondary (default) button style."""
        return f"""
            QPushButton {{
                background-color: {Colors.BORDER};
                color: {Colors.TEXT};
                font-size: {FontSize.SM}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: {BorderRadius.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
                max-height: {Size.INPUT_HEIGHT}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.HOVER};
                border-color: {Colors.BORDER_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.PRESSED};
            }}
            QPushButton:checked {{
                background-color: {Colors.ACCENT_BRIGHT};
                color: white;
                border-color: {Colors.ACCENT_BRIGHT};
            }}
            QPushButton:checked:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_LIGHT};
                color: {Colors.TEXT_DISABLED};
                border-color: {Colors.BORDER};
            }}
        """

    def _primary_style(self) -> str:
        """Primary button style (accent color)."""
        return f"""
            QPushButton {{
                background-color: {Colors.ACCENT_BRIGHT};
                color: white;
                font-size: {FontSize.SM}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.ACCENT_BRIGHT};
                border-radius: {BorderRadius.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
                max-height: {Size.INPUT_HEIGHT}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_HOVER};
                border-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.ACCENT};
            }}
            QPushButton:checked {{
                background-color: {Colors.ACCENT};
                border-color: {Colors.ACCENT};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BORDER};
                color: {Colors.TEXT_DISABLED};
                border-color: {Colors.BORDER};
            }}
        """

    def _danger_style(self) -> str:
        """Danger button style (red, for destructive actions)."""
        return f"""
            QPushButton {{
                background-color: {Colors.ERROR};
                color: {Colors.TEXT_BRIGHT};
                font-size: {FontSize.SM}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.ERROR};
                border-radius: {BorderRadius.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
                max-height: {Size.INPUT_HEIGHT}px;
            }}
            QPushButton:hover {{ background-color: {Colors.ERROR_HOVER}; }}
            QPushButton:pressed {{ background-color: {Colors.ERROR_PRESSED}; }}
            QPushButton:disabled {{ background-color: {Colors.BG_LIGHT}; color: {Colors.TEXT_DISABLED}; }}
        """

    def _success_style(self) -> str:
        """Success button style (green/teal, for positive actions)."""
        return f"""
            QPushButton {{
                background-color: {Colors.SUCCESS};
                color: {Colors.TEXT_BRIGHT};
                font-size: {FontSize.SM}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.SUCCESS};
                border-radius: {BorderRadius.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
                max-height: {Size.INPUT_HEIGHT}px;
            }}
            QPushButton:hover {{ background-color: {Colors.SUCCESS_HOVER}; }}
            QPushButton:pressed {{ background-color: {Colors.SUCCESS_PRESSED}; }}
            QPushButton:disabled {{ background-color: {Colors.BG_LIGHT}; color: {Colors.TEXT_DISABLED}; }}
        """

    def _ghost_style(self) -> str:
        """Ghost button style (transparent, text only)."""
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.TEXT_MUTED};
                font-size: {FontSize.SM}px;
                padding: 0px {Spacing.LG}px;
                border: none;
                border-radius: {BorderRadius.SM}px;
                min-height: {Size.INPUT_HEIGHT}px;
                max-height: {Size.INPUT_HEIGHT}px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT}; }}
            QPushButton:pressed {{ color: {Colors.TEXT_BRIGHT}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_DISABLED}; }}
        """

    @property
    def variant(self) -> str:
        """Get button variant."""
        return self._variant

    @variant.setter
    def variant(self, value: ButtonVariant) -> None:
        """Set button variant and update style."""
        self._variant = value
        self._apply_style()


class IconButton(QPushButton):
    """A compact icon/text button with minimal styling.

    Good for toolbars, overlay controls, or compact UI elements.

    Usage:
        btn = IconButton(icon=some_icon)
        btn = IconButton(icon=some_icon, size=24)
    """

    def __init__(
        self,
        icon: QIcon | None = None,
        text: str = "",
        size: int = 28,
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._size = size

        if icon is not None:
            self.setIcon(icon)

        self.setFixedSize(size, size)
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply icon button styling."""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(60, 60, 60, 0.8);
                color: {Colors.TEXT_BRIGHT};
                border: 1px solid rgba(80, 80, 80, 0.8);
                border-radius: {BorderRadius.SM}px;
                padding: {Spacing.XS}px;
            }}
            QPushButton:hover {{
                background-color: rgba(74, 74, 77, 0.9);
                border-color: rgba(96, 96, 96, 0.9);
            }}
            QPushButton:pressed {{
                background-color: rgba(45, 45, 48, 0.9);
            }}
            QPushButton:checked {{
                background-color: rgba(0, 120, 212, 0.9);
                border-color: rgba(0, 120, 212, 0.9);
            }}
        """)

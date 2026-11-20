"""Button components with consistent styling."""

from typing import Literal

import qtawesome as qta
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from .theme import BorderRadius, Colors, ControlSize, Spacing

ButtonVariant = Literal["primary", "secondary", "success", "danger", "ghost"]


class Button(QPushButton):
    """A styled button component with consistent appearance.

    Supports multiple visual variants for different contexts.

    Usage:
        btn = Button("Click Me")
        btn = Button("Submit", variant="primary")
        btn = Button("Cancel", variant="secondary")
        btn = Button("Halt", variant="danger")
        btn = Button("Start", variant="success", size=ControlSize.XL)
    """

    def __init__(
        self,
        text: str = "",
        variant: ButtonVariant = "secondary",
        icon: QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.LG,
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._variant = variant
        self._size = size

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
                font-size: {self._size.font}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.BORDER_FOCUS};
                border-radius: {self._size.radius}px;
                min-height: {self._size.h}px;
                max-height: {self._size.h}px;
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
                font-size: {self._size.font}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.ACCENT_BRIGHT};
                border-radius: {self._size.radius}px;
                min-height: {self._size.h}px;
                max-height: {self._size.h}px;
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
                font-size: {self._size.font}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.ERROR};
                border-radius: {self._size.radius}px;
                min-height: {self._size.h}px;
                max-height: {self._size.h}px;
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
                font-size: {self._size.font}px;
                padding: 0px {Spacing.LG}px;
                border: 1px solid {Colors.SUCCESS};
                border-radius: {self._size.radius}px;
                min-height: {self._size.h}px;
                max-height: {self._size.h}px;
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
                font-size: {self._size.font}px;
                padding: 0px {Spacing.LG}px;
                border: none;
                border-radius: {self._size.radius}px;
                min-height: {self._size.h}px;
                max-height: {self._size.h}px;
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
    """A compact icon button with minimal styling.

    Good for toolbars, overlay controls, or compact UI elements.
    Supports qtawesome icon names directly.

    Usage:
        btn = IconButton("mdi.folder")
        btn = IconButton("mdi.play", size=24)
        btn = IconButton(icon=some_qicon)  # Also accepts QIcon directly
    """

    def __init__(
        self,
        icon: str | QIcon | None = None,
        size: int = 28,
        color: str = Colors.TEXT_MUTED,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._size = size
        self._color = color
        self._icon_name: str | None = None

        if isinstance(icon, str):
            self._icon_name = icon
            self.setIcon(qta.icon(icon, color=color))
        elif icon is not None:
            self.setIcon(icon)

        self.setFixedSize(size, size)
        icon_size = int(size * 0.6)
        self.setIconSize(QSize(icon_size, icon_size))
        self._apply_style()

    def _apply_style(self) -> None:
        """Apply icon button styling."""
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: {BorderRadius.SM}px;
            }}
            QPushButton:hover {{
                background-color: {Colors.HOVER};
            }}
            QPushButton:pressed {{
                background-color: {Colors.PRESSED};
            }}
        """)

"""Button components with classmethod-based variant API."""

from dataclasses import dataclass, replace
from typing import Unpack

import qtawesome as qta
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QToolButton, QWidget
from typing_extensions import TypedDict

from .theme import Colors, ControlSize, Spacing


class Button(QPushButton):
    """A styled button component with consistent appearance.

    Usage:
        # Default (secondary)
        Button("OK")

        # Using classmethods
        Button.primary("Save")
        Button.primary("Save", size=ControlSize.LG)
        Button.secondary("Cancel")
        Button.ghost("Skip")
        Button.danger("Delete")
        Button.success("Confirm")

        # With overrides
        Button.primary("Save", bg_hover=Colors.SUCCESS)

        # Full custom fmt
        Button("Custom", fmt=Button.Fmt(bg=Colors.BG_DARK, fg=Colors.ACCENT))
    """

    class FmtOverrides(TypedDict, total=False):
        """Valid overrides for Button.Fmt."""

        bg: str
        fg: str
        bg_hover: str
        fg_hover: str
        bg_pressed: str
        border: str | None

    @dataclass(frozen=True)
    class Fmt:
        """Visual format for Button components."""

        bg: str = Colors.BORDER
        fg: str = Colors.TEXT
        bg_hover: str = Colors.HOVER
        fg_hover: str | None = None  # None = same as fg
        bg_pressed: str = Colors.PRESSED
        border: str | None = Colors.BORDER_FOCUS

        def with_(self, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            """Return a new format with overrides applied."""
            return replace(self, **overrides)

        @classmethod
        def primary(cls, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            fmt = cls(
                bg=Colors.ACCENT_BRIGHT,
                fg="white",
                bg_hover=Colors.ACCENT_HOVER,
                bg_pressed=Colors.ACCENT,
                border=Colors.ACCENT_BRIGHT,
            )
            return fmt.with_(**overrides) if overrides else fmt

        @classmethod
        def secondary(cls, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            fmt = cls(
                bg=Colors.BORDER,
                fg=Colors.TEXT,
                bg_hover=Colors.HOVER,
                bg_pressed=Colors.PRESSED,
                border=Colors.BORDER_FOCUS,
            )
            return fmt.with_(**overrides) if overrides else fmt

        @classmethod
        def success(cls, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            fmt = cls(
                bg=Colors.SUCCESS,
                fg=Colors.TEXT_BRIGHT,
                bg_hover=Colors.SUCCESS_HOVER,
                bg_pressed=Colors.SUCCESS_PRESSED,
                border=Colors.SUCCESS,
            )
            return fmt.with_(**overrides) if overrides else fmt

        @classmethod
        def danger(cls, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            fmt = cls(
                bg=Colors.ERROR,
                fg=Colors.TEXT_BRIGHT,
                bg_hover=Colors.ERROR_HOVER,
                bg_pressed=Colors.ERROR_PRESSED,
                border=Colors.ERROR,
            )
            return fmt.with_(**overrides) if overrides else fmt

        @classmethod
        def ghost(cls, **overrides: Unpack["Button.FmtOverrides"]) -> "Button.Fmt":
            fmt = cls(
                bg="transparent",
                fg=Colors.TEXT_MUTED,
                bg_hover="transparent",
                fg_hover=Colors.TEXT,
                bg_pressed="transparent",
                border=None,
            )
            return fmt.with_(**overrides) if overrides else fmt

    def __init__(
        self,
        text: str = "",
        *,
        fmt: "Button.Fmt | None" = None,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self._fmt = fmt or Button.Fmt()
        self._size = size
        self._icon_name: str | None = None

        if isinstance(icon, str):
            self._icon_name = icon
        elif icon is not None:
            self.setIcon(icon)

        if checkable:
            self.setCheckable(True)

        self._apply_style()

    def fmt(self, new_fmt: "Button.Fmt | None" = None, **overrides: Unpack[FmtOverrides]) -> "Button.Fmt":
        """Get current format, set a new format, or update with overrides."""
        if new_fmt is not None:
            self._fmt = new_fmt
            self._apply_style()
        elif overrides:
            self._fmt = self._fmt.with_(**overrides)
            self._apply_style()
        return self._fmt

    def _apply_style(self) -> None:
        """Apply styling based on format."""
        f = self._fmt
        s = self._size

        fg_hover = f.fg_hover or f.fg
        border = f"1px solid {f.border}" if f.border else f"1px solid {f.bg}"
        border_hover = f"1px solid {f.border}" if f.border else f"1px solid {f.bg_hover}"

        # Set icon with correct color if using qtawesome
        if self._icon_name:
            self.setIcon(qta.icon(self._icon_name, color=f.fg, color_active=fg_hover))

        self.setFixedHeight(s.h)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {f.bg};
                color: {f.fg};
                font-size: {s.font}px;
                padding: 0px {Spacing.LG}px;
                border: {border};
                border-radius: {s.radius}px;
            }}
            QPushButton:hover {{
                background-color: {f.bg_hover};
                color: {fg_hover};
                border: {border_hover};
            }}
            QPushButton:pressed {{
                background-color: {f.bg_pressed};
            }}
            QPushButton:checked {{
                background-color: {Colors.ACCENT_BRIGHT};
                color: white;
                border: 1px solid {Colors.ACCENT_BRIGHT};
            }}
            QPushButton:checked:hover {{
                background-color: {Colors.ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_LIGHT};
                color: {Colors.TEXT_DISABLED};
                border: 1px solid {Colors.BORDER};
            }}
        """)

    # --- Variant classmethods ---

    @classmethod
    def primary(
        cls,
        text: str = "",
        *,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Button":
        """Create a primary button (accent colored, prominent action)."""
        return cls(text, fmt=cls.Fmt.primary(**overrides), icon=icon, checkable=checkable, size=size, parent=parent)

    @classmethod
    def secondary(
        cls,
        text: str = "",
        *,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Button":
        """Create a secondary button (standard, default style)."""
        return cls(text, fmt=cls.Fmt.secondary(**overrides), icon=icon, checkable=checkable, size=size, parent=parent)

    @classmethod
    def success(
        cls,
        text: str = "",
        *,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Button":
        """Create a success button (green, for positive actions)."""
        return cls(text, fmt=cls.Fmt.success(**overrides), icon=icon, checkable=checkable, size=size, parent=parent)

    @classmethod
    def danger(
        cls,
        text: str = "",
        *,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Button":
        """Create a danger button (red, for destructive actions)."""
        return cls(text, fmt=cls.Fmt.danger(**overrides), icon=icon, checkable=checkable, size=size, parent=parent)

    @classmethod
    def ghost(
        cls,
        text: str = "",
        *,
        icon: str | QIcon | None = None,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Button":
        """Create a ghost button (transparent, minimal)."""
        return cls(text, fmt=cls.Fmt.ghost(**overrides), icon=icon, checkable=checkable, size=size, parent=parent)

    @classmethod
    def icon_btn(
        cls,
        name: str,
        *,
        size: ControlSize = ControlSize.SM,
        color: str = Colors.TEXT_MUTED,
        color_hover: str = Colors.TEXT,
        parent: QWidget | None = None,
    ) -> "Button":
        """Create a compact icon-only button.

        Usage:
            Button.icon_btn("mdi.folder")
            Button.icon_btn("mdi.play", size=24)
            Button.icon_btn("mdi.close", color=Colors.ERROR)
        """
        fmt = cls.Fmt(
            bg="transparent",
            fg=color,
            bg_hover=Colors.HOVER,
            fg_hover=color_hover,
            bg_pressed=Colors.PRESSED,
            border=None,
        )
        btn = cls("", fmt=fmt, icon=name, parent=parent)
        btn.setFixedSize(size.h, size.h)
        icon_size = int(size.h * 0.6)
        btn.setIconSize(QSize(icon_size, icon_size))
        return btn


class ToolButton(QToolButton):
    """A simple icon-only tool button using qtawesome icons.

    Usage:
        btn = ToolButton("mdi.play")
        btn = ToolButton(("mdi.lock", "mdi.lock-open"), checkable=True)
        btn = ToolButton("mdi.close", color=Colors.ERROR)
    """

    def __init__(
        self,
        icon: str | tuple[str, str],
        *,
        checkable: bool = False,
        size: ControlSize = ControlSize.MD,
        color: str = Colors.TEXT_MUTED,
        color_hover: str = Colors.TEXT,
        color_unchecked: str = Colors.TEXT_DISABLED,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if isinstance(icon, tuple):
            self._icon_name = icon[0]
            self._checked_icon_name: str | None = icon[1]
        else:
            self._icon_name = icon
            self._checked_icon_name = None
        self._size = size
        self._color = color
        self._color_hover = color_hover
        self._color_unchecked = color_unchecked

        if checkable:
            self.setCheckable(True)
            self.toggled.connect(self._on_toggled)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

    def _on_toggled(self, checked: bool) -> None:
        """Update icon when toggled."""
        self._update_icon(checked)

    def _update_icon(self, checked: bool = False) -> None:
        """Update the icon based on checked state."""
        icon_name = self._checked_icon_name if checked and self._checked_icon_name else self._icon_name
        color = self._color if (checked or not self.isCheckable()) else self._color_unchecked
        self.setIcon(qta.icon(icon_name, color=color, color_active=self._color_hover))

    def _apply_style(self) -> None:
        """Apply icon and stylesheet."""
        icon_size = int(self._size.h * 0.6)
        self._update_icon(self.isChecked())
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(self._size.h, self._size.h)
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: {self._size.radius}px;
                padding: 0px;
            }}
            QToolButton:hover {{
                background-color: {Colors.HOVER};
            }}
            QToolButton:pressed {{
                background-color: {Colors.PRESSED};
            }}
            QToolButton:checked {{
                background-color: {Colors.HOVER};
            }}
        """)

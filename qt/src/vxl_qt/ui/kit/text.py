"""Text component with style presets.

Provides a unified text display component with configurable typography.
"""

from dataclasses import dataclass, replace
from typing import Unpack

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget
from typing_extensions import TypedDict

from .theme import BorderRadius, Colors, FontSize, FontWeight, Spacing


class Text(QLabel):
    """Styled text display component.

    Usage:
        # Using presets
        Text.title("Camera Settings")
        Text.muted("Secondary info")
        Text.value("123.45")

        # Presets with overrides
        Text.title("Error!", color=Colors.ERROR)
        Text.muted("Warning", color=Colors.WARNING)

        # Full customization
        Text("Custom", fmt=Text.Fmt(size=20, weight=FontWeight.BOLD))
    """

    class FmtOverrides(TypedDict, total=False):
        """Valid overrides for Text.Fmt."""

        size: int
        weight: FontWeight
        color: str

    @dataclass(frozen=True)
    class Fmt:
        """Typography format for Text components."""

        size: int = FontSize.SM
        weight: FontWeight = FontWeight.NORMAL
        color: str = Colors.TEXT

        def with_(self, **overrides: Unpack["Text.FmtOverrides"]) -> "Text.Fmt":
            """Return a new format with overrides applied."""
            return replace(self, **overrides)

    def __init__(self, text: str = "", fmt: "Text.Fmt | None" = None, parent: QWidget | None = None) -> None:
        super().__init__(text, parent=parent)
        self._fmt = fmt or Text.Fmt(color=Colors.TEXT_MUTED)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._apply_fmt()

    @property
    def fmt(self) -> "Text.Fmt":
        """Return current text format."""
        return self._fmt

    @fmt.setter
    def fmt(self, fmt: "Text.Fmt") -> None:
        """Set new text format."""
        self._fmt = fmt
        self._apply_fmt()

    def _apply_fmt(self) -> None:
        """Apply current format to the label."""
        f = self._fmt
        self.setStyleSheet(f"QLabel {{ font-size: {f.size}px; font-weight: {f.weight.value}; color: {f.color}; }}")

    # Preset factory methods

    @classmethod
    def default(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create text with default format."""
        base = cls.Fmt(color=Colors.TEXT_MUTED)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)

    @classmethod
    def title(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create title text (large, bold)."""
        base = cls.Fmt(size=FontSize.LG, weight=FontWeight.BOLD, color=Colors.TEXT)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)

    @classmethod
    def heading(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create heading text (bright)."""
        base = cls.Fmt(color=Colors.TEXT)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)

    @classmethod
    def section(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create section header text (bold, muted)."""
        base = cls.Fmt(weight=FontWeight.BOLD, color=Colors.TEXT_MUTED)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)

    @classmethod
    def value(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create value text."""
        base = cls.Fmt(color=Colors.TEXT)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)

    @classmethod
    def muted(cls, text: str, parent: QWidget | None = None, **overrides: Unpack[FmtOverrides]) -> "Text":
        """Create muted text (small, dim)."""
        base = cls.Fmt(size=FontSize.XS, color=Colors.TEXT_MUTED)
        return cls(text, fmt=base.with_(**overrides) if overrides else base, parent=parent)


def _auto_text_color(bg_color: str) -> str:
    """Determine if text should be black or white based on background brightness."""
    bg_color = bg_color.lstrip("#")
    r, g, b = (int(bg_color[i : i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.55 else "#FFFFFF"


class Chip(QWidget):
    """Colored badge with auto-contrast text.

    Automatically calculates text color (black/white) based on background
    brightness for optimal contrast.

    Usage:
        Chip("560 nm", color="#BEF264")
        Chip("488 nm", color="#67e8f9", border_color="#0E7490")
    """

    def __init__(
        self,
        text: str,
        color: str = "#e0e0e0",
        border_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._border_color = border_color

        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self._text = Text(text)
        self._update_text_color()

        layout = QHBoxLayout(self)
        layout.addWidget(self._text)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)

    def _update_text_color(self) -> None:
        """Update text color based on background luminance."""
        text_color = _auto_text_color(self._color)
        self._text.fmt = Text.Fmt(size=FontSize.SM, color=text_color)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Draw the chip background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setBrush(QBrush(QColor(self._color)))

        if self._border_color:
            pen = QPen(QColor(self._border_color))
            pen.setWidth(2)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        radius = BorderRadius.MD
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)

        if event is not None:
            super().paintEvent(event)

    def setText(self, text: str) -> None:
        """Set the chip text."""
        self._text.setText(text)

    def text(self) -> str:
        """Get the chip text."""
        return self._text.text()

    def setColor(self, color: str, border_color: str | None = None) -> None:
        """Set the chip background color."""
        self._color = color
        self._border_color = border_color
        self._update_text_color()
        self.update()

    @classmethod
    def overlay(cls, text: str, parent: QWidget | None = None) -> "Chip":
        """Create an overlay-style chip (HUD text)."""
        chip = cls(text, color="rgba(0, 0, 0, 150)", parent=parent)
        chip._text.fmt = Text.Fmt(size=FontSize.SM, weight=FontWeight.BOLD, color=Colors.SUCCESS)
        return chip

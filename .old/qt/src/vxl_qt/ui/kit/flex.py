"""Alternative Flex API with classmethod presets and hover support.

This module explores a Text-like API for Flex components:
- Classmethods for common variants: Flex.card(...), Flex.row(...)
- Full customization via **fmt overrides: Flex.vstack(..., background=..., padding=...)
- Built-in hover state support
"""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Unpack

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QBrush, QColor, QEnterEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QVBoxLayout, QWidget
from typing_extensions import TypedDict

from .theme import BorderRadius, Colors, Spacing

# A child can be a widget or a (widget, stretch) tuple
BoxChild = QWidget | tuple[QWidget, int]


class Flow(Enum):
    """Direction of stack layout."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class Flex(QWidget):
    """Unified container with layout and optional visual styling.

    Usage:
        # Plain stacks
        Flex.vstack(widget1, widget2)
        Flex.hstack(btn1, btn2)

        # Card preset
        Flex.card(header, content)
        Flex.card(content, border_radius=BorderRadius.SM)

        # With styling overrides
        Flex.vstack(content, background=Colors.BG_DARK, border_radius=BorderRadius.LG)
        Flex.hstack(label, padding=(Spacing.LG, 0, 0, 0))
    """

    class FmtOverrides(TypedDict, total=False):
        """Valid overrides for Flex.Fmt."""

        background: str | None
        border_color: str | None
        border_radius: int
        border_width: int
        padding: tuple[int, int, int, int]
        hover: "Flex.FmtOverrides | None"

    @dataclass(frozen=True)
    class Fmt:
        """Visual format for Flex components."""

        background: str | None = None
        border_color: str | None = None
        border_radius: int = 0
        border_width: int = 1
        padding: tuple[int, int, int, int] = (0, 0, 0, 0)
        hover: "Flex.FmtOverrides | None" = None

        def with_(self, **overrides: Unpack["Flex.FmtOverrides"]) -> "Flex.Fmt":
            """Return a new format with overrides applied."""
            return replace(self, **overrides)

        @property
        def has_visuals(self) -> bool:
            """Check if this format has any visual styling."""
            return self.background is not None or self.border_color is not None

    def __init__(
        self,
        *children: BoxChild,
        flow: Flow = Flow.VERTICAL,
        spacing: int = Spacing.SM,
        fmt: "Flex.Fmt | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fmt = fmt or Flex.Fmt()
        self._flow = flow
        self._hovered = False

        # Only set transparent background if no visual styling
        if not self._fmt.has_visuals:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Enable mouse tracking for hover detection
        if self._fmt.hover:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        # Create layout based on flow direction
        layout = QHBoxLayout(self) if flow == Flow.HORIZONTAL else QVBoxLayout(self)

        # Apply padding from format as margins
        layout.setContentsMargins(*self._fmt.padding)
        layout.setSpacing(spacing)

        # Add children
        if children:
            self.add(*children)

    @property
    def fmt(self) -> "Flex.Fmt":
        """Return current format."""
        return self._fmt

    def add(self, *children: BoxChild) -> None:
        """Add one or more children to the stack."""
        layout = self.layout()
        if not isinstance(layout, QBoxLayout):
            return

        for child in children:
            if isinstance(child, tuple):
                widget, stretch = child
                if isinstance(widget, Stretch):
                    layout.addStretch(stretch)
                else:
                    layout.addWidget(widget, stretch)
            elif isinstance(child, Stretch):
                layout.addStretch()
            else:
                layout.addWidget(child)

    def add_stretch(self, stretch: int = 1) -> None:
        """Add a stretch to the stack."""
        layout = self.layout()
        if isinstance(layout, QBoxLayout):
            layout.addStretch(stretch)

    def clear(self) -> None:
        """Remove all children from the stack."""
        layout = self.layout()
        if not isinstance(layout, QBoxLayout):
            return

        while layout.count() > 0:
            item = layout.takeAt(0)
            if item and (widget := item.widget()):
                widget.deleteLater()

    def enterEvent(self, event: QEnterEvent | None) -> None:
        """Handle mouse enter for hover state."""
        if self._fmt.hover:
            self._hovered = True
            self.update()
        if event:
            super().enterEvent(event)

    def leaveEvent(self, event: QEvent | None) -> None:
        """Handle mouse leave for hover state."""
        if self._fmt.hover:
            self._hovered = False
            self.update()
        if event:
            super().leaveEvent(event)

    def _active_fmt(self) -> "Flex.Fmt":
        """Get the currently active format (base or hover)."""
        if self._hovered and self._fmt.hover:
            overrides = {**self._fmt.hover, "hover": None}
            return self._fmt.with_(**overrides)
        return self._fmt

    def paintEvent(self, event: QPaintEvent | None) -> None:
        """Custom paint for styled stacks."""
        fmt = self._active_fmt()

        if not fmt.has_visuals:
            if event is not None:
                super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Set up brush for background
        if fmt.background:
            painter.setBrush(QBrush(QColor(fmt.background)))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # Set up pen for border
        if fmt.border_color:
            pen = QPen(QColor(fmt.border_color))
            pen.setWidth(fmt.border_width)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        # Draw rounded rect
        adj = fmt.border_width // 2 + 1
        rect = self.rect().adjusted(adj, adj, -adj, -adj)
        painter.drawRoundedRect(rect, fmt.border_radius, fmt.border_radius)

        if event is not None:
            super().paintEvent(event)

    # --- Preset factory methods ---

    @classmethod
    def vstack(
        cls,
        *children: BoxChild,
        spacing: int = Spacing.SM,
        parent: QWidget | None = None,
        **fmt: Unpack[FmtOverrides],
    ) -> "Flex":
        """Create a vertical stack (plain)."""
        return cls(*children, flow=Flow.VERTICAL, spacing=spacing, fmt=cls.Fmt(**fmt) if fmt else None, parent=parent)

    @classmethod
    def hstack(
        cls,
        *children: BoxChild,
        spacing: int = Spacing.SM,
        parent: QWidget | None = None,
        **fmt: Unpack[FmtOverrides],
    ) -> "Flex":
        """Create a horizontal stack (plain)."""
        return cls(*children, flow=Flow.HORIZONTAL, spacing=spacing, fmt=cls.Fmt(**fmt) if fmt else None, parent=parent)

    @classmethod
    def card(
        cls,
        *children: BoxChild,
        flow: Flow = Flow.VERTICAL,
        spacing: int = Spacing.SM,
        parent: QWidget | None = None,
        **overrides: Unpack[FmtOverrides],
    ) -> "Flex":
        """Create a card-styled stack."""
        base = cls.Fmt(
            background=Colors.BG_MEDIUM,
            border_color=Colors.BORDER,
            border_radius=BorderRadius.LG,
            padding=(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD),
        )
        fmt = base.with_(**overrides) if overrides else base
        return cls(*children, flow=flow, spacing=spacing, fmt=fmt, parent=parent)


class Stretch(QWidget):
    """Spacer widget that expands to fill available space."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

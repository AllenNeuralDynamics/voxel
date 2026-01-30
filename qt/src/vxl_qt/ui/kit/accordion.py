"""Accordion component for collapsible sections."""

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from .text import Text
from .theme import Colors, Size, Spacing


class Accordion(QWidget):
    """Minimal collapsible section with clickable header.

    Just handles expand/collapse behavior - no borders, no backgrounds.
    Parent container (e.g., CardDark) provides visual styling.

    Usage:
        accordion = Accordion("Frame Size", summary_value="1024 x 1024 px")
        accordion.content_layout.addWidget(HBox(Label("Sensor"), Stretch(), sensor_value))
        accordion.content_layout.addWidget(some_control)

    Args:
        label: Header label text.
        summary_value: Optional value shown right-aligned in header.
        expanded: Initial expanded state.
        parent: Parent widget.
    """

    toggled = Signal(bool)

    def __init__(
        self,
        label: str,
        summary_value: str = "",
        expanded: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._expanded = expanded

        # Make widget transparent (no background)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header (clickable)
        self._header = QWidget()
        self._header.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._header.setCursor(self.cursor().shape())
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, Spacing.XS, 0, Spacing.XS)
        header_layout.setSpacing(Spacing.XS)

        # Label
        self._label = Text.muted(label)
        header_layout.addWidget(self._label)

        # Chevron button
        self._chevron = QToolButton()
        self._chevron.setFixedSize(Size.SM, Size.SM)
        self._chevron.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
        """)
        self._update_chevron()
        header_layout.addWidget(self._chevron)

        header_layout.addStretch()

        # Summary value (right-aligned)
        self._summary_label = Text.value(summary_value, color=Colors.TEXT_MUTED)
        header_layout.addWidget(self._summary_label)

        main_layout.addWidget(self._header)

        # Content area
        self._content = QWidget()
        self._content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, Spacing.XS, 0, 0)
        self._content_layout.setSpacing(Spacing.XS)
        main_layout.addWidget(self._content)

        # Set initial visibility
        self._content.setVisible(self._expanded)

        # Connect signals
        self._header.mousePressEvent = self._on_header_clicked
        self._chevron.clicked.connect(self._toggle)

    def _on_header_clicked(self, _event) -> None:
        """Handle header click."""
        self._toggle()

    def _toggle(self) -> None:
        """Toggle expanded state."""
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_chevron()
        self.toggled.emit(self._expanded)

    def _update_chevron(self) -> None:
        """Update chevron icon based on expanded state."""
        icon_name = "mdi6.chevron-down" if self._expanded else "mdi6.chevron-right"
        self._chevron.setIcon(qta.icon(icon_name, color=Colors.TEXT_MUTED))
        self._chevron.setIconSize(self._chevron.size())

    def set_summary(self, value: str) -> None:
        """Update the summary value shown in header."""
        self._summary_label.setText(value)

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically expand/collapse."""
        if self._expanded != expanded:
            self._toggle()

    def is_expanded(self) -> bool:
        """Return current expanded state."""
        return self._expanded

    @property
    def content_layout(self) -> QVBoxLayout:
        """Return layout for adding content widgets."""
        return self._content_layout

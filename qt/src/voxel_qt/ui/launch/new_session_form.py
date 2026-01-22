"""New session form for creating sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)
from voxel_qt.ui.primitives.buttons import Button
from voxel_qt.ui.primitives.display import Label
from voxel_qt.ui.primitives.input import Select
from voxel_qt.ui.theme import BorderRadius, Colors, FontSize

if TYPE_CHECKING:
    from voxel_studio.system import SessionRoot


class NewSessionForm(QWidget):
    """Form for creating a new session.

    Emits:
        session_requested: (root_name, session_name, rig_config) when Create is clicked
    """

    session_requested = Signal(str, str, str)  # root_name, session_name, rig_config

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._roots: list[SessionRoot] = []
        self._rigs: list[str] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the form UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Form container with border
        form_container = QWidget()
        form_container.setStyleSheet(f"""
            QWidget {{
                background-color: {Colors.BG_MEDIUM};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
            }}
        """)
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setSpacing(12)

        # Root selector
        root_row = QHBoxLayout()
        root_row.setSpacing(8)

        root_label = Label("Root:", variant="muted")
        root_label.setFixedWidth(80)
        root_row.addWidget(root_label)

        self._root_select = Select()
        root_row.addWidget(self._root_select, stretch=1)

        form_layout.addLayout(root_row)

        # Session name input
        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        name_label = Label("Name:", variant="muted")
        name_label.setFixedWidth(80)
        name_row.addWidget(name_label)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("session-name")
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG_LIGHT};
                border: 1px solid {Colors.BORDER};
                border-radius: {BorderRadius.MD}px;
                padding: 6px 10px;
                color: {Colors.TEXT};
                font-size: {FontSize.MD}px;
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
        name_row.addWidget(self._name_input, stretch=1)

        form_layout.addLayout(name_row)

        # Rig config selector
        rig_row = QHBoxLayout()
        rig_row.setSpacing(8)

        rig_label = Label("Rig Config:", variant="muted")
        rig_label.setFixedWidth(80)
        rig_row.addWidget(rig_label)

        self._rig_select = Select()
        rig_row.addWidget(self._rig_select, stretch=1)

        form_layout.addLayout(rig_row)

        # Create button
        button_row = QHBoxLayout()
        button_row.addStretch()

        self._create_btn = Button("Create Session", variant="primary")
        self._create_btn.clicked.connect(self._on_create_clicked)
        button_row.addWidget(self._create_btn)

        form_layout.addLayout(button_row)

        layout.addWidget(form_container)

        # Update button state based on inputs
        self._name_input.textChanged.connect(self._update_button_state)
        self._update_button_state()

    def set_roots(self, roots: list[SessionRoot]) -> None:
        """Update available session roots."""
        self._roots = roots
        # Create options with display text and values
        options = [(root.label or root.name, root.name) for root in roots]
        self._root_select.clear()
        for display, value in options:
            self._root_select.addItem(display, value)

    def set_rigs(self, rigs: list[str]) -> None:
        """Update available rig configurations."""
        self._rigs = rigs
        self._rig_select.clear()
        for rig in rigs:
            self._rig_select.addItem(rig, rig)

    def _update_button_state(self) -> None:
        """Enable/disable create button based on form validity."""
        name = self._name_input.text().strip()
        has_root = self._root_select.count() > 0
        has_rig = self._rig_select.count() > 0
        self._create_btn.setEnabled(bool(name) and has_root and has_rig)

    def _on_create_clicked(self) -> None:
        """Handle create button click."""
        root_name = self._root_select.currentData()
        session_name = self._name_input.text().strip()
        rig_config = self._rig_select.currentData()

        if root_name and session_name and rig_config:
            self.session_requested.emit(root_name, session_name, rig_config)

    def clear(self) -> None:
        """Clear the form."""
        self._name_input.clear()

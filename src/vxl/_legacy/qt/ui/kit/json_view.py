"""JSON/dictionary viewer widget with collapsible tree structure."""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .text import FontSize
from .theme import BorderRadius, Colors, Spacing


class JsonView(QWidget):
    """Read-only tree viewer for JSON-compatible data.

    Displays dicts, lists, and primitives in a collapsible two-column tree.
    Container nodes show a count summary and expand to reveal children.

    Usage:
        view = JsonView()
        view.set_data({
            "name": "MockDev1",
            "pins": {"ao0": {"pin": "ao0", "path": "/dev/ao0"}},
            "available": ["ao2", "ao3", "ao6"],
        })

        # Update later
        view.set_data(new_data)

    Args:
        data: Initial data to display.
        expand_depth: Number of tree levels to expand initially (0 = all collapsed).
        show_header: Whether to show the Key/Value column header.
        parent: Parent widget.
    """

    def __init__(
        self,
        data: Any = None,
        expand_depth: int = 1,
        show_header: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._expand_depth = expand_depth
        self._setup_ui(show_header)
        if data is not None:
            self.set_data(data)

    def _setup_ui(self, show_header: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Key", "Value"])
        self._tree.setHeaderHidden(not show_header)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(False)
        self._tree.setIndentation(Spacing.LG)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self._tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self._tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        self._apply_style()
        layout.addWidget(self._tree)

    def _apply_style(self) -> None:
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: {BorderRadius.SM}px;
                outline: none;
                font-size: {FontSize.SM}px;
            }}
            QTreeWidget::item {{
                padding: {Spacing.XS}px 0;
            }}
            QTreeWidget::item:hover {{
                background-color: {Colors.HOVER};
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_MEDIUM};
                color: {Colors.TEXT_MUTED};
                border: none;
                border-bottom: 1px solid {Colors.BORDER};
                padding: {Spacing.XS}px {Spacing.SM}px;
                font-size: {FontSize.XS}px;
            }}
        """)

    def set_data(self, data: Any) -> None:
        """Replace displayed data and rebuild the tree."""
        self._tree.clear()
        if isinstance(data, dict):
            for key, value in data.items():
                self._add_node(self._tree.invisibleRootItem(), str(key), value)
        elif isinstance(data, (list, tuple)):
            for i, value in enumerate(data):
                self._add_node(self._tree.invisibleRootItem(), str(i), value)
        else:
            self._tree.addTopLevelItem(QTreeWidgetItem(["", _format_primitive(data)]))
        if self._expand_depth > 0:
            self._tree.expandToDepth(self._expand_depth - 1)

    def expand_all(self) -> None:
        """Expand all tree nodes."""
        self._tree.expandAll()

    def collapse_all(self) -> None:
        """Collapse all tree nodes."""
        self._tree.collapseAll()

    def _add_node(self, parent: QTreeWidgetItem, key: str, value: Any) -> None:
        """Recursively add a key-value node to the tree."""
        if isinstance(value, dict):
            item = QTreeWidgetItem(parent, [key, f"{{{len(value)}}}"])
            item.setForeground(1, QColor(str(Colors.TEXT_MUTED)))
            for k, v in value.items():
                self._add_node(item, str(k), v)
        elif isinstance(value, (list, tuple)):
            item = QTreeWidgetItem(parent, [key, f"[{len(value)}]"])
            item.setForeground(1, QColor(str(Colors.TEXT_MUTED)))
            for i, v in enumerate(value):
                self._add_node(item, str(i), v)
        else:
            QTreeWidgetItem(parent, [key, _format_primitive(value)])


def _format_primitive(value: Any) -> str:
    """Format a primitive value for display."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

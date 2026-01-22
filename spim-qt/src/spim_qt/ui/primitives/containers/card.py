"""Card container component."""

from typing import Literal

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QVBoxLayout, QWidget

from spim_qt.ui.theme import BorderRadius, Colors, FontSize, Spacing


class Card(QFrame):
    """Titled card container with vertical or horizontal content flow.

    Usage:
        # Vertical (default)
        Card("Subject",
            Field("Subject ID", self._subject_id),
            Field("Notes", self._notes),
        )

        # Horizontal
        Card("Chamber",
            Field("Medium", self._medium),
            Field("Index", self._index),
            flow="horizontal",
        )

        # Untitled
        Card(None, self._widget)
    """

    def __init__(
        self,
        title: str | None,
        *children: QWidget | QLayout,
        flow: Literal["vertical", "horizontal"] = "vertical",
        spacing: int = 8,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._title = title

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        main_layout.setSpacing(Spacing.SM)

        # Title label
        self._title_label = QLabel(title or "")
        self._title_label.setObjectName("cardTitle")
        self._title_label.setVisible(title is not None)
        main_layout.addWidget(self._title_label)

        # Content layout (vertical or horizontal)
        content = QWidget()
        content_layout = QHBoxLayout(content) if flow == "horizontal" else QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(spacing)

        for child in children:
            if isinstance(child, QLayout):
                content_layout.addLayout(child)
            else:
                content_layout.addWidget(child)

        main_layout.addWidget(content)

        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            Card {{
                background-color: {Colors.BG_MEDIUM};
                border: 1px solid {Colors.BORDER};
                border-radius: {BorderRadius.SM}px;
            }}
            #cardTitle {{
                font-size: {FontSize.MD}px;
                font-weight: 600;
                color: {Colors.TEXT};
                padding-bottom: {Spacing.SM}px;
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)

    @property
    def title(self) -> str | None:
        return self._title

    @title.setter
    def title(self, value: str | None) -> None:
        self._title = value
        self._title_label.setText(value or "")
        self._title_label.setVisible(value is not None)

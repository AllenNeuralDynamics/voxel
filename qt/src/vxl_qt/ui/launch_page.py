"""Launch page for session management.

The launch page is shown when no session is active. It allows users to:
- Create new sessions
- Resume existing sessions
- View application logs

This is a pure view component that emits signals for user actions.
The parent (MainWindow) handles orchestration with VoxelQtApp.
"""

import typing
from typing import Any, cast, get_args, get_origin

from pydantic_core import PydanticUndefined
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QBoxLayout, QLabel, QScrollArea, QWidget

from vxl.metadata import BASE_METADATA_TARGET, ExperimentMetadata, resolve_metadata_class
from vxl.system import SessionDirectory, SessionRoot
from vxl_qt.ui.assets import VOXEL_LOGO
from vxl_qt.ui.kit import (
    Button,
    Colors,
    ControlSize,
    DoubleSpinBox,
    Flex,
    Flow,
    FormBuilder,
    LinearLoader,
    Select,
    Spacing,
    SpinBox,
    Splitter,
    Stretch,
    Text,
    TextArea,
    TextInput,
    hbox,
    vbox,
)
from vxl_qt.ui.panels import LogPanel
from vxlib import display_name, format_relative_time


class _StringListInput(QWidget):
    """Input widget for list[str] fields (e.g. experimenters).

    Vertical stack of TextInput rows, each with a remove button.
    An "Add" ghost button at the bottom appends new rows.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[TextInput, Button]] = []

        self._container = Flex.vstack(spacing=Spacing.SM)
        self._add_btn = Button.ghost("+ Add")
        self._add_btn.clicked.connect(lambda _checked: self._add_row())

        layout = vbox(self, spacing=Spacing.SM)
        layout.addWidget(self._container)
        layout.addWidget(self._add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._add_row()

    def _add_row(self, text: str = "") -> None:
        inp = TextInput(text=text)
        remove_btn = Button.icon_btn("mdi.close")
        row = Flex.hstack(inp, remove_btn, spacing=Spacing.SM)

        inp.textChanged.connect(self._on_changed)
        remove_btn.clicked.connect(lambda: self._remove_row(row, inp))

        self._rows.append((inp, remove_btn))
        self._container.add(row)
        self._on_changed()

    def _remove_row(self, row: Flex, inp: TextInput) -> None:
        container_layout = cast("QBoxLayout", self._container.layout())
        container_layout.removeWidget(row)
        row.deleteLater()
        self._rows = [(i, b) for i, b in self._rows if i is not inp]
        self._on_changed()

    def _on_changed(self) -> None:
        has_empty = any(not inp.text().strip() for inp, _ in self._rows)
        self._add_btn.setEnabled(not has_empty)
        self.changed.emit()

    def get_values(self) -> list[str]:
        return [inp.text().strip() for inp, _ in self._rows if inp.text().strip()]

    def set_values(self, values: list[str]) -> None:
        # Clear existing rows
        container_layout = cast("QBoxLayout", self._container.layout())
        while container_layout.count() > 0:
            item = container_layout.takeAt(0)
            if item and (widget := item.widget()):
                widget.deleteLater()
        self._rows.clear()

        for v in values:
            self._add_row(v)
        if not values:
            self._add_row()


class MetadataForm(QWidget):
    """Dynamic form generated from a pydantic model's fields."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widgets: dict[str, QWidget] = {}
        self._layout = vbox(self, spacing=Spacing.MD)

    def set_metadata_class(self, cls: type[ExperimentMetadata] | None) -> None:
        # Clear existing form
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item and (widget := item.widget()):
                widget.deleteLater()
        self._widgets.clear()

        if cls is None:
            return

        builder = FormBuilder()
        # session_name is a top-level input; experimenters and notes are appended at end
        _tail = ("session_name", "experimenters", "notes")
        fields = [(n, f) for n, f in cls.model_fields.items() if n not in _tail]
        for tail_name in ("experimenters", "notes"):
            if tail_name in cls.model_fields:
                fields.append((tail_name, cls.model_fields[tail_name]))

        for name, field_info in fields:
            widget = self._build_field_widget(name, field_info)
            if widget is not None:
                if field_info.description:
                    widget.setToolTip(field_info.description)
                self._widgets[name] = widget
                # Notes uses placeholder text instead of a label
                if name == "notes":
                    self._layout.addWidget(widget)
                else:
                    builder.field(display_name(name), widget)

        form_widget = builder.build()
        self._layout.insertWidget(0, form_widget)

    def _build_field_widget(self, name: str, field_info: Any) -> QWidget | None:
        """Create an appropriate widget for a pydantic field."""
        annotation = field_info.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)

        if annotation is str and name == "notes":
            w = TextArea(placeholder="Experiment notes...")
            if field_info.default is not PydanticUndefined and field_info.default:
                w.setPlainText(str(field_info.default))
            w.textChanged.connect(self.changed.emit)
            return w

        if annotation is str:
            w = TextInput()
            if field_info.default is not PydanticUndefined:
                w.setText(str(field_info.default))
            w.textChanged.connect(self.changed.emit)
            return w

        if annotation is float:
            w = DoubleSpinBox(decimals=3, step=0.01, min_val=-1e9, max_val=1e9)
            if field_info.default is not PydanticUndefined:
                w.setValue(float(field_info.default))
            w.valueChanged.connect(self.changed.emit)
            return w

        if annotation is int:
            w = SpinBox(min_val=-999999, max_val=999999)
            if field_info.default is not PydanticUndefined:
                w.setValue(int(field_info.default))
            w.valueChanged.connect(self.changed.emit)
            return w

        if origin is list and args and args[0] is str:
            w = _StringListInput()
            if field_info.default_factory is not None:
                w.set_values(field_info.default_factory())
            w.changed.connect(self.changed.emit)
            return w

        if get_origin(annotation) is typing.Literal:
            options = list(get_args(annotation))
            w = Select(options=[(v, str(v)) for v in options])
            if field_info.default is not PydanticUndefined and field_info.default in options:
                w.set_value(field_info.default)
            w.value_changed.connect(self.changed.emit)
            return w

        return None

    def get_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, TextArea):
                values[name] = widget.toPlainText()
            elif isinstance(widget, TextInput):
                values[name] = widget.text()
            elif isinstance(widget, (DoubleSpinBox, SpinBox)):
                values[name] = widget.value()
            elif isinstance(widget, _StringListInput):
                values[name] = widget.get_values()
            elif isinstance(widget, Select):
                values[name] = widget.get_value()
        return values


class LaunchHeader(Flex):
    """Header with logo, title, and swappable status line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        logo = QLabel()
        pixmap = QPixmap(str(VOXEL_LOGO))
        pixmap = pixmap.scaledToWidth(40, Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(pixmap)

        # Status line: swaps between idle and launching
        self._idle_text = Text.muted("Select or create a session to get started")
        self._launching_indicator = Flex.vstack(
            Text.muted("Starting session..."),
            LinearLoader(),
            spacing=Spacing.SM,
        )
        self._launching_indicator.hide()

        super().__init__(
            Flex.hstack(
                logo,
                Flex.vstack(
                    Text.title("Voxel", color=Colors.TEXT_BRIGHT),
                    Text.muted("Light sheet microscope control"),
                    spacing=Spacing.XS,
                ),
                Stretch(),
                spacing=Spacing.LG,
            ),
            self._idle_text,
            self._launching_indicator,
            spacing=Spacing.MD,
            parent=parent,
        )

    def set_launching(self, launching: bool) -> None:
        """Toggle between idle and launching status line."""
        self._idle_text.setVisible(not launching)
        self._launching_indicator.setVisible(launching)


class NewSessionForm(QWidget):
    """Form for creating a new session."""

    session_requested = Signal(str, str, str, str, object)  # root, rig, name, target, metadata

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._roots: list[SessionRoot] = []
        self._rigs: list[str] = []

        # Create widgets
        self._root_select = Select(size=ControlSize.LG)
        self._rig_select = Select(size=ControlSize.LG)
        self._name_input = TextInput(placeholder="optional", size=ControlSize.LG)
        self._metadata_select = Select(size=ControlSize.LG)
        self._metadata_form = MetadataForm()
        self._create_btn = Button.primary("Create Session", size=ControlSize.LG)
        self._path_preview = Text.muted("")

        # Row 1: Root selector + Rig selector + Session name + Metadata schema (equal width)
        root_field = Flex.vstack(Text.muted("Session Root"), self._root_select, spacing=Spacing.SM)
        rig_field = Flex.vstack(Text.muted("Rig Configuration"), self._rig_select, spacing=Spacing.SM)
        name_field = Flex.vstack(Text.muted("Session Name (optional)"), self._name_input, spacing=Spacing.SM)
        metadata_field = Flex.vstack(Text.muted("Metadata Schema"), self._metadata_select, spacing=Spacing.SM)
        row1 = Flex.hstack((root_field, 1), (rig_field, 1), (name_field, 1), (metadata_field, 1), spacing=Spacing.XL)

        # Row 2: MetadataForm (full width)
        row2 = self._metadata_form

        # Row 3: Path preview + Create button
        row3 = Flex.hstack(
            self._path_preview,
            Stretch(),
            self._create_btn,
            spacing=Spacing.XL,
        )

        # Form container with card styling
        form = Flex.card(
            row1,
            row2,
            row3,
            spacing=Spacing.LG,
            padding=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL),
        )

        layout = vbox(self)
        layout.addWidget(form)

        # Initialize metadata select (will be populated by set_metadata_targets)

        self._update_button_state()
        self._connect_signals()
        self._metadata_form.set_metadata_class(ExperimentMetadata)

    def _connect_signals(self) -> None:
        self._create_btn.clicked.connect(self._on_create_clicked)
        self._root_select.value_changed.connect(lambda _: self._on_form_changed())
        self._rig_select.value_changed.connect(lambda _: self._on_form_changed())
        self._name_input.textChanged.connect(self._update_path_preview)
        self._metadata_select.value_changed.connect(self._on_metadata_target_changed)
        self._metadata_form.changed.connect(self._update_path_preview)

    def set_roots(self, roots: list[SessionRoot]) -> None:
        self._roots = roots
        self._root_select.clear()
        for root in roots:
            self._root_select.addItem(root.label or root.name, root.name)
        self._on_form_changed()

    def set_rigs(self, rigs: list[str]) -> None:
        self._rigs = rigs
        self._rig_select.clear()
        for rig in rigs:
            self._rig_select.addItem(rig, rig)
        self._on_form_changed()

    def set_metadata_targets(self, targets: dict[str, str]) -> None:
        options = [(path, display_name(name)) for name, path in targets.items()]
        self._metadata_select.set_options(options)

    def _on_metadata_target_changed(self, target: object) -> None:
        try:
            cls = resolve_metadata_class(str(target))
        except Exception:
            cls = ExperimentMetadata
        self._metadata_form.set_metadata_class(cls)
        self._update_path_preview()

    def _on_form_changed(self) -> None:
        self._update_button_state()
        self._update_path_preview()

    def _update_button_state(self) -> None:
        has_root = self._root_select.count() > 0
        has_rig = self._rig_select.count() > 0
        self._create_btn.setEnabled(has_root and has_rig)

    def _update_path_preview(self) -> None:
        root_name = self._root_select.currentData()
        rig_name = self._rig_select.currentData()
        target = self._metadata_select.get_value()
        session_name = self._name_input.text().strip()
        values = self._metadata_form.get_values()

        if not root_name or not rig_name:
            self._path_preview.setText("")
            return

        root = next((r for r in self._roots if r.name == root_name), None)
        if root is None:
            self._path_preview.setText("")
            return

        try:
            cls = resolve_metadata_class(str(target))
            meta = cls(**values)
            parts = [rig_name, meta.uid(), session_name]
            folder = "-".join(p for p in parts if p)
            self._path_preview.setText(str(root.path / folder))
        except Exception:
            self._path_preview.setText("")

    def _on_create_clicked(self) -> None:
        root_name = self._root_select.currentData()
        rig_config = self._rig_select.currentData()
        session_name = self._name_input.text().strip()
        metadata_target = self._metadata_select.get_value() or BASE_METADATA_TARGET
        metadata = self._metadata_form.get_values()

        if root_name and rig_config:
            self.session_requested.emit(root_name, rig_config, session_name, metadata_target, metadata)

    def clear(self) -> None:
        self._name_input.clear()
        self._metadata_form.set_metadata_class(None)


class SessionCard(Flex):
    """Clickable card displaying a session with resume/folder actions."""

    clicked = Signal(object)  # SessionDirectory

    def __init__(self, session: SessionDirectory, parent: QWidget | None = None) -> None:
        # Folder button
        folder_btn = Button.icon_btn("mdi.folder-outline")
        folder_btn.setToolTip(str(session.path))
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(session.path))))

        # Resume button
        resume_btn = Button.ghost("Resume")
        resume_btn.clicked.connect(lambda: self.clicked.emit(session))

        # Row format with hover effect
        fmt = Flex.Fmt(
            background="transparent",
            border_color=Colors.BORDER,
            border_width=0,
            padding=(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD),
            hover={"background": Colors.BG_LIGHT},
        )

        super().__init__(
            Text(display_name(session.name)),
            Text.muted(session.root_name),
            Stretch(),
            Text.muted(format_relative_time(session.modified)),
            folder_btn,
            resume_btn,
            flow=Flow.HORIZONTAL,
            spacing=Spacing.LG,
            fmt=fmt,
            parent=parent,
        )

        self._session = session
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._session)
        super().mousePressEvent(event)


class SessionsList(QScrollArea):
    """Scrollable list of session cards."""

    session_selected = Signal(object)  # SessionDirectory

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = Flex.card(spacing=0, padding=(1, 1, 1, 1))
        self.setWidget(self._container)
        self._cards: list[SessionCard] = []

    def set_sessions(self, sessions: list[SessionDirectory]) -> None:
        """Update the list with new sessions."""
        container_layout = cast("QBoxLayout", self._container.layout())

        # Clear existing cards
        for card in self._cards:
            container_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        # Remove any remaining items (stretch, empty label)
        while container_layout.count() > 0:
            item = container_layout.takeAt(0)
            if item and (widget := item.widget()):
                widget.deleteLater()

        # Add new session cards
        for session in sessions:
            card = SessionCard(session)
            card.clicked.connect(self.session_selected.emit)
            self._cards.append(card)
            self._container.add(card)

        # Add stretch at end
        self._container.add_stretch()

        # Show empty state if no sessions
        if not sessions:
            empty_label = Text.muted("No recent sessions")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.insertWidget(0, empty_label)


class LaunchPage(QWidget):
    """Launch page for session management.

    A pure view component that emits signals for user actions.
    The parent (MainWindow) handles orchestration with VoxelApp.

    Signals:
        new_session_requested: Emitted when user submits the new session form.
        session_resumed: Emitted when user clicks on an existing session.

    Layout:
        - Left panel (40%): Header + new session form + recent sessions list
        - Right panel (60%): Log viewer
    """

    # User intent signals
    new_session_requested = Signal(str, str, str, str, object)  # root, rig, name, target, metadata
    session_resumed = Signal(object)  # SessionDirectory

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Create widgets
        self._splitter = Splitter()
        self._left_panel = QWidget()
        self._right_panel = QWidget()

        self._header = LaunchHeader()

        self._new_session_form = NewSessionForm()
        self._form_section = Flex.vstack(
            Text.section("New Session", color=Colors.TEXT),
            self._new_session_form,
            spacing=Spacing.MD,
        )

        self._sessions_list = SessionsList()
        self._sessions_section = Flex.vstack(
            Text.section("Recent Sessions", color=Colors.TEXT),
            self._sessions_list,
            spacing=Spacing.MD,
        )

        self._log_panel = LogPanel()

        self._configure_layout()
        self._connect_signals()

    def _configure_layout(self) -> None:
        layout = hbox(self)

        # Left panel layout
        left_layout = vbox(
            self._left_panel, spacing=Spacing.XXL, margins=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        )
        left_layout.addWidget(self._header)
        left_layout.addWidget(self._form_section)
        left_layout.addWidget(self._sessions_section, stretch=1)
        left_layout.addStretch()

        self._left_panel.setMinimumWidth(800)
        self._left_panel.setStyleSheet(f"background-color: {Colors.BG_MEDIUM};")
        self._splitter.addWidget(self._left_panel)

        # Right panel layout
        right_layout = vbox(self._right_panel, margins=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL))
        right_layout.addWidget(self._log_panel)

        self._right_panel.setMinimumWidth(400)
        self._right_panel.setStyleSheet(f"background-color: {Colors.BG_DARK};")
        self._splitter.addWidget(self._right_panel)

        # Default split: left 800px, right gets remainder
        self._splitter.setSizes([800, 1120])

        layout.addWidget(self._splitter)

    def _connect_signals(self) -> None:
        # Forward child signals as page-level signals
        self._new_session_form.session_requested.connect(self.new_session_requested.emit)
        self._sessions_list.session_selected.connect(self.session_resumed.emit)

    def set_roots(self, roots: list[SessionRoot]) -> None:
        """Set available session roots in the form."""
        self._new_session_form.set_roots(roots)

    def set_rigs(self, rigs: list[str]) -> None:
        """Set available rig configurations in the form."""
        self._new_session_form.set_rigs(rigs)

    def set_metadata_targets(self, targets: dict[str, str]) -> None:
        """Set available metadata targets in the form."""
        self._new_session_form.set_metadata_targets(targets)

    def set_sessions(self, sessions: list[SessionDirectory]) -> None:
        """Set the list of recent sessions."""
        self._sessions_list.set_sessions(sessions)

    def set_launching(self, launching: bool) -> None:
        """Toggle between idle and launching states."""
        self._header.set_launching(launching)
        self._form_section.setVisible(not launching)
        self._sessions_section.setVisible(not launching)

"""Launch page for session management.

The launch page is shown when no session is active. It allows users to:
- Create new sessions
- Resume existing sessions
- View application logs

This is a pure view component that emits signals for user actions.
The parent (MainWindow) handles orchestration with VoxelQtApp.
"""

from typing import cast

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QBoxLayout, QLabel, QScrollArea, QWidget
from voxel_studio.system import SessionDirectory, SessionRoot

from voxel_qt.ui.assets import VOXEL_LOGO
from voxel_qt.ui.kit import (
    Box,
    Button,
    Colors,
    ControlSize,
    Flow,
    LinearLoader,
    Select,
    Spacing,
    Splitter,
    Stretch,
    Text,
    TextInput,
    hbox,
    vbox,
)
from voxel_qt.ui.panels import LogPanel
from vxlib import display_name, format_relative_time


class LaunchHeader(Box):
    """Header with logo and title/subtitle."""

    def __init__(self, parent: QWidget | None = None) -> None:
        logo = QLabel()
        pixmap = QPixmap(str(VOXEL_LOGO))
        pixmap = pixmap.scaledToWidth(40, Qt.TransformationMode.SmoothTransformation)
        logo.setPixmap(pixmap)

        super().__init__(
            logo,
            Box.vstack(
                Text.title("Voxel Qt", color=Colors.TEXT_BRIGHT),
                Text.muted("Select or create a session to get started"),
                spacing=Spacing.XS,
            ),
            Stretch(),
            flow=Flow.HORIZONTAL,
            spacing=Spacing.LG,
            parent=parent,
        )


class NewSessionForm(QWidget):
    """Form for creating a new session."""

    session_requested = Signal(str, str, str)  # root_name, session_name, rig_config

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._roots: list[SessionRoot] = []
        self._rigs: list[str] = []

        # Create widgets
        self._root_select = Select(size=ControlSize.LG)
        self._name_input = TextInput(placeholder="session-name", size=ControlSize.LG)
        self._rig_select = Select(size=ControlSize.LG)
        self._create_btn = Button.primary("Create Session", size=ControlSize.LG)
        self._path_preview = Text.muted("")

        # Row 1: Root selector + Rig selector side by side
        root_field = Box.vstack(Text.muted("Session Root"), self._root_select, spacing=Spacing.SM)
        rig_field = Box.vstack(Text.muted("Rig Configuration"), self._rig_select, spacing=Spacing.SM)
        row1 = Box.hstack(root_field, rig_field, spacing=Spacing.XL)

        # Row 2: Session name + Create button side by side
        row2 = Box.hstack(
            Box.vstack(Text.muted("Session Name"), self._name_input, spacing=Spacing.SM),
            Box.vstack(Stretch(), self._create_btn),
            spacing=Spacing.XL,
        )

        # Form container with card styling
        form = Box.card(
            row1,
            row2,
            self._path_preview,
            spacing=Spacing.LG,
            padding=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL),
        )

        layout = vbox(self)
        layout.addWidget(form)

        self._update_button_state()
        self._connect_signals()

    def _connect_signals(self) -> None:
        self._create_btn.clicked.connect(self._on_create_clicked)
        self._name_input.textChanged.connect(self._on_form_changed)
        self._root_select.currentIndexChanged.connect(self._on_form_changed)

    def set_roots(self, roots: list[SessionRoot]) -> None:
        self._roots = roots
        self._root_select.clear()
        for root in roots:
            self._root_select.addItem(root.label or root.name, root.name)

    def set_rigs(self, rigs: list[str]) -> None:
        self._rigs = rigs
        self._rig_select.clear()
        for rig in rigs:
            self._rig_select.addItem(rig, rig)

    def _on_form_changed(self) -> None:
        self._update_button_state()
        self._update_path_preview()

    def _update_button_state(self) -> None:
        name = self._name_input.text().strip()
        has_root = self._root_select.count() > 0
        has_rig = self._rig_select.count() > 0
        self._create_btn.setEnabled(bool(name) and has_root and has_rig)

    def _update_path_preview(self) -> None:
        root_name = self._root_select.currentData()
        session_name = self._name_input.text().strip()

        if not root_name or not session_name:
            self._path_preview.setText("")
            return

        root = next((r for r in self._roots if r.name == root_name), None)
        if root is None:
            self._path_preview.setText("")
            return

        sanitized = session_name.lower().replace(" ", "-")
        full_path = root.path / sanitized
        self._path_preview.setText(f"{full_path}")

    def _on_create_clicked(self) -> None:
        root_name = self._root_select.currentData()
        session_name = self._name_input.text().strip()
        rig_config = self._rig_select.currentData()

        if root_name and session_name and rig_config:
            self.session_requested.emit(root_name, session_name, rig_config)

    def clear(self) -> None:
        self._name_input.clear()


class LaunchingIndicator(Box):
    """Centered loading indicator with animated progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            # Text.title("Starting Session...", color=Colors.TEXT_BRIGHT),
            # Text.muted("Initializing rig and devices..."),
            LinearLoader(),
            Stretch(),
            spacing=Spacing.MD,
            parent=parent,
        )


class SessionCard(Box):
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
        fmt = Box.Fmt(
            background="transparent",
            border_color=Colors.BORDER,
            border_width=0,
            padding=(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD),
            hover={"background": Colors.BG_LIGHT},
        )

        super().__init__(
            Text(display_name(session.name)),
            Text.muted(session.root_name),
            Text.muted(session.rig_name),
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

        self._container = Box.card(spacing=0, padding=(1, 1, 1, 1))
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
    The parent (MainWindow) handles orchestration with VoxelQtApp.

    Signals:
        new_session_requested: Emitted when user submits the new session form.
        session_resumed: Emitted when user clicks on an existing session.

    Layout:
        - Left panel (40%): Header + new session form + recent sessions list
        - Right panel (60%): Log viewer
    """

    # User intent signals
    new_session_requested = Signal(str, str, str)  # root_name, session_name, rig_config
    session_resumed = Signal(object)  # SessionDirectory

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Create widgets
        self._splitter = Splitter()
        self._left_panel = QWidget()
        self._right_panel = QWidget()

        self._header = LaunchHeader()
        self._launching_indicator = LaunchingIndicator()
        self._launching_indicator.hide()

        self._new_session_form = NewSessionForm()
        self._form_section = Box.vstack(
            Text.section("New Session", color=Colors.TEXT),
            self._new_session_form,
            spacing=Spacing.MD,
        )

        self._sessions_list = SessionsList()
        self._sessions_section = Box.vstack(
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
        left_layout.addWidget(self._launching_indicator, stretch=1)
        left_layout.addWidget(self._form_section)
        left_layout.addWidget(self._sessions_section, stretch=1)

        self._left_panel.setStyleSheet(f"background-color: {Colors.BG_MEDIUM};")
        self._splitter.addWidget(self._left_panel)

        # Right panel layout
        right_layout = vbox(self._right_panel, margins=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL))
        right_layout.addWidget(self._log_panel)

        self._right_panel.setStyleSheet(f"background-color: {Colors.BG_DARK};")
        self._splitter.addWidget(self._right_panel)

        # Set initial sizes (40% / 60%)
        self._splitter.setSizes([400, 600])

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

    def set_sessions(self, sessions: list[SessionDirectory]) -> None:
        """Set the list of recent sessions."""
        self._sessions_list.set_sessions(sessions)

    def set_launching(self, launching: bool) -> None:
        """Toggle between idle and launching states."""
        self._launching_indicator.setVisible(launching)
        self._form_section.setVisible(not launching)
        self._sessions_section.setVisible(not launching)

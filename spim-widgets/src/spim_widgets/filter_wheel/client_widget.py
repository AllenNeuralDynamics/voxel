"""Filter wheel widget using DeviceHandle."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from pyrig import DeviceHandle
from pyrig.device import PropsResponse
from spim_widgets.base import RemoteHandleAdapter, RemoteHandleWidget
from spim_widgets.filter_wheel.client_adapter import DiscreteAxisClientAdapter
from spim_widgets.filter_wheel.graphic import WheelGraphic


class FilterWheelClientWidget(RemoteHandleWidget):
    """Filter wheel control widget using DeviceHandle.

    Features:
    - Visual wheel graphic showing slots and assignments
    - Click to select slots
    - Step left/right buttons
    - Reset rotation button
    - Automatic property updates via subscription
    """

    def __init__(
        self,
        handle: DeviceHandle,
        hues: dict[str, int | float] | None = None,
        parent=None,
    ) -> None:
        self._hues: dict[str, float | int] = {
            "655LP": 0,  # red (0 degrees)
            "620/60BP": 120,  # green (120 degrees)
            "500LP": 230,  # blue (240 degrees)
        }
        if hues is not None:
            self._hues.update(hues)

        self._slot_count = 6  # Default, will be updated
        self._labels: dict[int, str | None] = {}
        self._current_position = 0

        super().__init__(handle, parent)

    def _create_adapter(self, handle: DeviceHandle) -> RemoteHandleAdapter:
        """Create discrete axis adapter."""
        return DiscreteAxisClientAdapter(handle, parent=self)

    def _setup_ui(self) -> None:
        """Setup the filter wheel widget UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Wheel graphic
        self._graphic = WheelGraphic(
            num_slots=self._slot_count,
            assignments=self._labels,
            hue_mapping=self._hues,
        )
        self._graphic.selected_changed.connect(self._on_graphic_selection)
        layout.addWidget(self._graphic)

        # Controls
        layout.addLayout(self._create_controls_ui())

    def _create_controls_ui(self) -> QVBoxLayout:
        """Create control buttons."""
        controls_layout = QVBoxLayout()
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Row 1 - Step controls
        left_btn = QPushButton("◀")
        left_btn.setToolTip("Spin left")
        left_btn.clicked.connect(self._on_step_next)

        right_btn = QPushButton("▶")
        right_btn.setToolTip("Spin right")
        right_btn.clicked.connect(self._on_step_previous)

        row_1_layout = QHBoxLayout()
        row_1_layout.addWidget(left_btn)
        row_1_layout.addStretch()
        row_1_layout.addWidget(right_btn)

        # Row 2 - Reset and Status
        reset_btn = QPushButton("⟳")
        reset_btn.setToolTip("Reset wheel rotation")
        reset_btn.clicked.connect(self._on_reset)

        self._status_label = QLabel("Hover over circles to see labels, click to select")

        row_2_layout = QHBoxLayout()
        row_2_layout.addWidget(self._status_label)
        row_2_layout.addStretch()
        row_2_layout.addWidget(reset_btn)

        controls_layout.addLayout(row_1_layout)
        controls_layout.addLayout(row_2_layout)

        return controls_layout

    def _on_step_next(self) -> None:
        """Handle step next button click."""
        self._graphic.step_to_next()

    def _on_step_previous(self) -> None:
        """Handle step previous button click."""
        self._graphic.step_to_previous()

    def _on_reset(self) -> None:
        """Handle reset button click."""
        self._graphic.reset_rotation()

    def _on_graphic_selection(self) -> None:
        """Handle selection from graphic widget."""
        if (slot := self._graphic.selected_slot) is not None:
            self.adapter.moveToSlot(slot)

    def _on_properties_changed(self, props: PropsResponse) -> None:
        """Handle property updates from device."""
        # Update position
        if "position" in props.res:
            position = props.res["position"].value
            if position != self._current_position:
                self._current_position = position
                self._graphic.selected_slot = position

        # Update slot count (shouldn't change, but good to have)
        if "slot_count" in props.res:
            slot_count = props.res["slot_count"].value
            if slot_count != self._slot_count:
                self._slot_count = slot_count
                self._recreate_graphic()

        # Update labels
        if "labels" in props.res:
            labels = props.res["labels"].value
            # Convert string keys to integers if necessary
            labels_converted = {int(k) if isinstance(k, str) else k: v for k, v in labels.items()}
            if labels_converted != self._labels:
                self._labels = labels_converted
                self._recreate_graphic()

        # Update is_moving status
        if "is_moving" in props.res:
            is_moving = props.res["is_moving"].value
            if is_moving:
                self._status_label.setText("Moving...")
            else:
                label = self._labels.get(self._current_position, "Unknown")
                self._status_label.setText(f"Position: {self._current_position} ({label})")

    def _recreate_graphic(self) -> None:
        """Recreate the wheel graphic with updated slot count or labels."""
        # Remove old graphic
        old_graphic = self._graphic
        layout = self.layout()
        if layout is not None:
            layout.removeWidget(old_graphic)
        old_graphic.deleteLater()

        # Create new graphic
        self._graphic = WheelGraphic(
            num_slots=self._slot_count,
            assignments=self._labels,
            hue_mapping=self._hues,
        )
        self._graphic.selected_changed.connect(self._on_graphic_selection)
        self._graphic.selected_slot = self._current_position

        # Insert at position 0 (before controls)
        # We know the layout is QVBoxLayout from _setup_ui, so we can safely cast
        if isinstance(layout, QVBoxLayout):
            layout.insertWidget(0, self._graphic)

    @property
    def adapter(self) -> DiscreteAxisClientAdapter:
        """Access the discrete axis adapter with proper typing."""
        return self._adapter  # type: ignore

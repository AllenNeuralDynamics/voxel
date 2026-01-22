"""Filter wheel device control widget."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from voxel_qt.ui.controls.filter_wheel.graphic import WheelGraphic

if TYPE_CHECKING:
    from voxel_qt.handle import DeviceHandleQt

log = logging.getLogger(__name__)


class FilterWheelControl(QWidget):
    """Filter wheel device control widget.

    Wraps a WheelGraphic with device communication via DeviceHandleQt.
    Works with any DiscreteAxis device (filter wheels, objective turrets, etc.).

    Args:
        adapter: DeviceHandleQt wrapping a DiscreteAxis device.
        hue_mapping: Optional mapping of filter labels to hue values (0-360).
        parent: Parent widget.

    Example (integrated with voxel-qt):
        adapter = devices_manager.get_adapter("filter_wheel_1")
        widget = FilterWheelControl(adapter)

    Example (standalone):
        from voxel_drivers.axes.simulated import SimulatedDiscreteAxis
        from voxel_qt.handle import create_local_handle, DeviceHandleQt

        device = SimulatedDiscreteAxis(uid="fw", slots={0: "GFP", 1: "RFP"}, slot_count=6)
        handle = create_local_handle(device)
        adapter = DeviceHandleQt(handle)
        await adapter.start()
        widget = FilterWheelControl(adapter)
    """

    def __init__(
        self,
        adapter: DeviceHandleQt,
        hue_mapping: Mapping[str, float | int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._hue_mapping = hue_mapping or {}
        self._initialized = False

        # Placeholder until we get device info
        self._graphic: WheelGraphic | None = None
        self._status_label: QLabel | None = None

        self._setup_ui()
        self._connect_signals()

        # Trigger async initialization
        asyncio.create_task(self._initialize())

    def _setup_ui(self) -> None:
        """Set up the initial UI (placeholder until device info is fetched)."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder label shown while loading
        self._loading_label = QLabel("Loading filter wheel...")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._loading_label)

    def _connect_signals(self) -> None:
        """Connect to adapter signals."""
        self._adapter.properties_changed.connect(self._on_properties_changed)
        self._adapter.fault.connect(self._on_fault)

    async def _initialize(self) -> None:
        """Fetch device info and build the full UI."""
        try:
            # Fetch device properties
            slot_count = await self._adapter.get("slot_count")
            labels = await self._adapter.get("labels")
            position = await self._adapter.get("position")

            log.debug(
                "FilterWheelControl init: slot_count=%s, labels=%s, position=%s",
                slot_count,
                labels,
                position,
            )

            # Remove loading placeholder
            self._loading_label.deleteLater()

            # Build the real UI
            self._build_wheel_ui(slot_count, labels, position)
            self._initialized = True

        except Exception:
            log.exception("Failed to initialize FilterWheelControl")
            self._loading_label.setText("Error loading filter wheel")

    def _build_wheel_ui(
        self,
        slot_count: int,
        labels: dict[int, str | None],
        current_position: int,
    ) -> None:
        """Build the wheel graphic and controls after fetching device info."""
        # Normalize labels dict (keys might be strings from JSON)
        normalized_labels: dict[int, str | None] = {int(k): v for k, v in labels.items()}

        # Create the wheel graphic
        self._graphic = WheelGraphic(
            num_slots=slot_count,
            assignments=normalized_labels,
            hue_mapping=self._hue_mapping,
        )
        self._graphic.selected_changed.connect(self._on_slot_selected)

        # Set initial position without animation
        self._graphic.set_selected_slot_no_animation(current_position)

        self._layout.addWidget(self._graphic)

        # Create controls
        controls_layout = QVBoxLayout()
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Row 1: Step controls
        row1 = QHBoxLayout()

        prev_btn = QPushButton("◀")
        prev_btn.setToolTip("Previous slot")
        prev_btn.clicked.connect(self._graphic.step_to_previous)
        row1.addWidget(prev_btn)

        row1.addStretch()

        next_btn = QPushButton("▶")
        next_btn.setToolTip("Next slot")
        next_btn.clicked.connect(self._graphic.step_to_next)
        row1.addWidget(next_btn)

        controls_layout.addLayout(row1)

        # Row 2: Status and reset
        row2 = QHBoxLayout()

        self._status_label = QLabel("")
        self._update_status_label(current_position)
        row2.addWidget(self._status_label)

        row2.addStretch()

        reset_btn = QPushButton("⟳")
        reset_btn.setToolTip("Reset to first slot")
        reset_btn.clicked.connect(self._graphic.reset_rotation)
        row2.addWidget(reset_btn)

        controls_layout.addLayout(row2)

        self._layout.addLayout(controls_layout)

    def _update_status_label(self, position: int) -> None:
        """Update the status label with current position info."""
        if self._status_label is None or self._graphic is None:
            return
        label = self._graphic.get_slot_label(position)
        self._status_label.setText(f"Position {position}: {label}")

    def _on_properties_changed(self, props: dict[str, Any]) -> None:
        """Handle property updates from the device."""
        if not self._initialized or self._graphic is None:
            return

        if "position" in props:
            position = int(props["position"])
            # Only update if different from current graphic state
            # to avoid fighting with user interactions
            if self._graphic.selected_slot != position:
                self._graphic.set_selected_slot_no_animation(position)
            self._update_status_label(position)

    def _on_slot_selected(self, slot: int) -> None:
        """Handle user selecting a slot in the graphic."""
        log.debug("User selected slot %s", slot)
        asyncio.create_task(self._move_to_slot(slot))

    async def _move_to_slot(self, slot: int) -> None:
        """Send move command to the device."""
        try:
            await self._adapter.call("move", slot)
        except Exception:
            log.exception("Failed to move to slot %s", slot)

    def _on_fault(self, message: str) -> None:
        """Handle adapter fault."""
        log.error("Filter wheel fault: %s", message)
        if self._status_label is not None:
            self._status_label.setText(f"Error: {message}")


# Demo code for standalone testing
if __name__ == "__main__":
    import sys

    from PySide6.QtWidgets import QApplication, QMainWindow
    from qasync import QEventLoop, asyncSlot
    from voxel_qt.handle import DeviceHandleQt

    from pyrig import create_local_handle

    class FilterWheelDemo(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Filter Wheel Control Demo")
            self.setGeometry(100, 100, 400, 500)

        @asyncSlot()
        async def setup(self) -> None:
            # Import here to avoid circular imports in demo
            from voxel_drivers.axes.simulated import SimulatedDiscreteAxis

            # Create simulated device
            device = SimulatedDiscreteAxis(
                uid="demo-fw",
                slots={0: "GFP", 1: "RFP", 2: "DAPI", 3: "Cy5"},
                slot_count=6,
            )

            # Create local handle and Qt adapter
            handle = create_local_handle(device)
            self._adapter = DeviceHandleQt(handle)
            await self._adapter.start()

            # Create the control widget
            hue_mapping = {
                "GFP": 120,  # Green
                "RFP": 0,  # Red
                "DAPI": 240,  # Blue
                "Cy5": 300,  # Magenta
            }
            widget = FilterWheelControl(self._adapter, hue_mapping=hue_mapping)
            self.setCentralWidget(widget)

    app = QApplication(sys.argv)

    # Set up async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    demo = FilterWheelDemo()
    demo.show()

    # Trigger async setup
    asyncio.ensure_future(demo.setup())

    with loop:
        loop.run_forever()

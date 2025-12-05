import colorsys
import logging
import math
from collections.abc import Mapping
from functools import cached_property

from PySide6.QtCore import QEasingCurve, QEvent, QRectF, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget


class WheelGraphic(QWidget):
    """A refined wheel widget with predefined members and no dynamic addition/removal."""

    selected_changed = Signal(int)  # Emits the position
    highlighted_changed = Signal(int)  # Emits the position of the highlighted slot

    def __init__(
        self,
        num_slots: int,
        assignments: Mapping[int, str | None],
        hue_mapping: Mapping[str, float | int] | None = None,
        start_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the wheel widget.

        Args:
            num_slots: Total number of slots on the wheel
            assignments: Dictionary mapping position -> label string (0-based indexing by default).
                Use None or "Empty" (case-insensitive) to indicate empty slots.
            hue_mapping: Dictionary mapping label -> hue value (0-360).
                Defaults to blue-grey (240) if label not found in mapping.
            start_index: The starting index for slots (default is 0)
            parent: Parent widget

        """
        super().__init__(parent)
        self.log = logging.getLogger("WheelGraphic")
        self.setMinimumSize(200, 200)

        self._start_index = start_index
        self._num_slots = num_slots

        self.log.debug("Slots: %s", self.slots)

        for position in assignments:
            if position not in self.slots:
                msg = f"Slot position {position} must be within {self.slots}"
                raise ValueError(msg)

        # Core widget data
        self.assignments = {i: assignments.get(i) for i in self.slots}

        self.default_hue = 240  # Blue-grey for unmapped labels (fallback color)
        self.hue_mapping = hue_mapping if hue_mapping else {}

        self.orbit_radius = 60
        self.desired_spacing = 12.0  # Desired spacing between members in SVG units
        self.show_info_text = False

        # Display and rendering
        self.renderer = QSvgRenderer()
        self.slot_positions: list[
            tuple[float, float, float, int]
        ] = []  # (x, y, radius, member_index) tuples for click detection

        # Rotation state
        self.angle_offset = 0

        # Animation system
        self._target_angle = 0
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate_step)
        self._is_animating = False
        self._animation_start_angle = 0
        self._animation_total_distance = 0
        self._animation_duration = 1000  # milliseconds
        self._animation_elapsed = 0
        self._easing_curve = QEasingCurve(QEasingCurve.Type.InOutCubic)

        # User interaction state
        self._selected_slot: int | None = None  # Track which is currently active (None means none)
        self._highlighted_slot: int | None = None
        self._pending_slot: int | None = None  # Slot that is pending selection after animation
        self._hovered_slot: int | None = None  # None means none

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        self.update_svg()

    @cached_property
    def slots(self) -> list[int]:
        return [self._start_index + k for k in range(self._num_slots)]

    @property
    def slot_size(self) -> float:
        """Get the automatically calculated slot size."""
        return self._compute_slot_radius()

    @property
    def selected_slot(self) -> int | None:
        """Get the currently active slot (1-based index), returns 0 if none."""
        return self._selected_slot if self._selected_slot in self.slots else None

    @selected_slot.setter
    def selected_slot(self, slot: int) -> None:
        """Set the currently active slot (1-based index)."""
        lo, hi = self._start_index, self.slots[-1]
        slot = int(min(max(slot, lo), hi))
        self._rotate_to_position(slot=slot, clockwise=None)

    def get_slot_label(self, slot_index: int) -> str:
        """Get the label for a slot at the given position."""
        label = self.assignments.get(slot_index)
        return label if label is not None else "Empty"

    def get_selected_slot_label(self) -> str | None:
        """Get the currently active slot label, returns None if none."""
        return self.get_slot_label(self.selected_slot) if self.selected_slot else None

    def reset_rotation(self) -> None:
        """Reset rotation to put the first slot at 12 o'clock."""
        self.selected_slot = self._start_index

    def step_to_next(self) -> None:
        if self._num_slots <= 0:
            return
        last_idx = self.slots[-1]
        current_slot = self.selected_slot if self.selected_slot is not None else self._start_index - 1
        next_potential = current_slot + 1
        if next_potential > last_idx:
            next_potential = self._start_index
        elif next_potential < self._start_index:
            next_potential = last_idx
        self._rotate_to_position(slot=next_potential, clockwise=None)

    def step_to_previous(self) -> None:
        if self._num_slots <= 0:
            return

        last_idx = self.slots[-1]
        current_slot = self.selected_slot if self.selected_slot is not None else self._start_index - 1
        next_potential = current_slot - 1
        if next_potential < self._start_index:
            next_potential = last_idx
        elif next_potential > last_idx:
            next_potential = self._start_index
        self._rotate_to_position(slot=next_potential, clockwise=None)

    def _normalized_index(self, index: int) -> int:
        """Compute a normalized index for the given slot index."""
        if self._num_slots <= 0:
            return 0
        return (index - self._start_index) % self._num_slots

    def update_svg(self) -> None:
        """Generate SVG with members at current rotation."""
        circles = []
        center_x, center_y = 100, 100  # SVG center

        # Get theme colors
        colors = self._get_theme_colors()

        # Get text color from theme
        text_color = self.palette().color(QPalette.ColorRole.Text).name()

        # Clear previous slot positions
        self.slot_positions = []
        highlighted_slot = self._nearest_top_slot()
        for slot_idx in self.slots:
            # Angle step from 0..N-1 based on offset
            base_angle = (360 / self._num_slots) * self._normalized_index(slot_idx)
            current_angle = base_angle + self.angle_offset - 90
            angle_rad = math.radians(current_angle)

            # Calculate position
            x = center_x + self.orbit_radius * math.cos(angle_rad)
            y = center_y + self.orbit_radius * math.sin(angle_rad)

            self.slot_positions.append((x, y, self.slot_size, slot_idx))  # for click detection

            # Check if this slot is hovered
            is_hovered = slot_idx == self._hovered_slot

            filled_slot_label = self.assignments.get(slot_idx)
            # Treat "Empty" or empty string as None (truly empty slot)
            if filled_slot_label and filled_slot_label.strip().lower() != "empty":
                label = filled_slot_label
                hue = self.hue_mapping.get(label, self.default_hue)

                h = hue / 360.0
                s = 0.7
                lightness = 0.6
                r, g, b = colorsys.hls_to_rgb(h, lightness, s)
                stroke_color = f"rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)})"

                # Set visual properties based on state
                # if is_highlighted:
                if slot_idx == highlighted_slot:
                    # Highlighted: filled circle with full opacity
                    fill_color = stroke_color
                    stroke_opacity = 1.0
                    stroke_width = 2
                else:
                    # Not highlighted: only stroke, no fill
                    fill_color = "none"
                    stroke_opacity = 1.0 if is_hovered else 0.5
                    stroke_width = 2
            else:
                # Empty slot: transparent with very dim stroke using theme color
                fill_color = "none"
                stroke_color = colors["wheel_stroke"]
                stroke_opacity = 0.5
                stroke_width = 1

            circles.append(f"""
                <circle
                    cx="{x:.1f}" cy="{y:.1f}" r="{self.slot_size:.1f}"
                    fill="{fill_color}" stroke="{stroke_color}"
                    stroke-width="{stroke_width}" stroke-opacity="{stroke_opacity}"
                />
            """)

        # Calculate the outer wheel radius and cutout properties
        wheel_outer_radius = self.orbit_radius + self.slot_size * 1.5  # Wheel extends beyond member orbit
        wheel_inner_radius = 10  # Inner hole radius
        cutout_radius = self.slot_size + self.desired_spacing / 2  # Selected Cutout slightly larger than member circles
        cutout_center_x = center_x  # Cutout at 12 o'clock position
        cutout_center_y = center_y - self.orbit_radius  # At 12 o'clock on the orbit

        # Wheel with cutout using SVG path - outer circle minus the inner hole and the cutout
        wheel_path = f"""
            M {center_x - wheel_outer_radius} {center_y}
            A {wheel_outer_radius} {wheel_outer_radius} 0 1 1 {center_x + wheel_outer_radius} {center_y}
            A {wheel_outer_radius} {wheel_outer_radius} 0 1 1 {center_x - wheel_outer_radius} {center_y}
            Z
            M {center_x - wheel_inner_radius} {center_y}
            A {wheel_inner_radius} {wheel_inner_radius} 0 1 0 {center_x + wheel_inner_radius} {center_y}
            A {wheel_inner_radius} {wheel_inner_radius} 0 1 0 {center_x - wheel_inner_radius} {center_y}
            Z
            M {cutout_center_x - cutout_radius} {cutout_center_y}
            A {cutout_radius} {cutout_radius} 0 1 0 {cutout_center_x + cutout_radius} {cutout_center_y}
            A {cutout_radius} {cutout_radius} 0 1 0 {cutout_center_x - cutout_radius} {cutout_center_y}
            Z
        """

        info_text = f"""
        <text x="100" y="25" text-anchor="middle" font-size="12" fill="{text_color}">
            {self._num_slots} slots, Selected: {self.selected_slot} ({self.get_selected_slot_label()})
        </text>
        """

        svg_data = f"""
        <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <!-- Gradient for the wheel using theme colors -->
                <radialGradient id="wheelGradient" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" style="stop-color:{colors["wheel_light"]};stop-opacity:1" />
                    <stop offset="85%" style="stop-color:{colors["wheel_base"]};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{colors["wheel_dark"]};stop-opacity:1" />
                </radialGradient>
            </defs>

            <!-- Outer wheel with cutouts -->
            <path d="{wheel_path}"
                  fill="url(#wheelGradient)"
                  stroke="{colors["wheel_stroke"]}"
                  stroke-width="1"
                  fill-rule="evenodd"/>

            <!-- Central point -->
            <circle cx="100" cy="100" r="3" fill="{text_color}" opacity="0.7"/>

            <!-- Member circles -->
            {"".join(circles)}

            <!-- Info text -->
            {info_text if self.show_info_text else ""}
        </svg>
        """

        self.renderer.load(svg_data.encode("utf-8"))
        self.update()

        if highlighted_slot != self._highlighted_slot:
            self._highlighted_slot = highlighted_slot
            if highlighted_slot in self.slots:
                self.highlighted_changed.emit(highlighted_slot)

    def _animate_step(self) -> None:
        """Animation step with Qt easing curve transition."""
        self._animation_elapsed += 50  # 50ms per frame

        if self._animation_elapsed >= self._animation_duration:
            # Animation complete
            self.angle_offset = self._target_angle
            self._animation_timer.stop()
            self._is_animating = False
            self._emit_selection_change()
        else:
            # Calculate progress (0.0 to 1.0)
            progress = self._animation_elapsed / self._animation_duration

            # Apply Qt easing curve
            eased_progress = self._easing_curve.valueForProgress(progress)

            # Calculate current angle based on eased progress
            angle_traveled = self._animation_total_distance * eased_progress
            self.angle_offset = (self._animation_start_angle + angle_traveled) % 360

        self.update_svg()

    def _emit_selection_change(self) -> None:
        if self._pending_slot is not None and self._pending_slot != self._selected_slot:
            self._selected_slot = self._pending_slot
            self.selected_changed.emit(self._selected_slot)
            self._pending_slot = None

    def _rotate_to_position(self, slot: int, clockwise: bool | None = None) -> None:
        """Start animation to target position with easing.

        Args:
            slot: The position to rotate to (1 to num_slots)
            clockwise: Direction to rotate. If None, uses shortest path.
                      If True, forces clockwise rotation.
                      If False, forces counter-clockwise rotation.

        """
        if slot not in self.slots:
            return
        self._pending_slot = slot
        # Calculate the angle needed to move this position to 12 o'clock
        # Convert 1-based position to 0-based for angle calculation
        position_base_angle = (360 / self._num_slots) * self._normalized_index(slot)
        # We want this position at angle 0 (after the -90 offset in update_svg)
        target_angle = (-position_base_angle) % 360

        self._target_angle = target_angle % 360

        # Calculate distances in both directions
        clockwise_distance = (self._target_angle - self.angle_offset) % 360
        counter_clockwise_distance = (self.angle_offset - self._target_angle) % 360

        # Determine which direction and distance to use
        if clockwise is None:
            if clockwise_distance <= counter_clockwise_distance:
                self._animation_total_distance = clockwise_distance
            else:
                self._animation_total_distance = -counter_clockwise_distance
        elif clockwise:
            self._animation_total_distance = clockwise_distance
        else:
            self._animation_total_distance = -counter_clockwise_distance

        # Skip animation if distance is very small
        if abs(self._animation_total_distance) < 1:
            self.angle_offset = self._target_angle
            self._emit_selection_change()
            return

        # Set up animation
        self._animation_start_angle = self.angle_offset
        self._animation_elapsed = 0

        # Adjust duration based on distance (longer distances take more time)
        # Base duration of 800ms, with additional time for longer rotations
        self._animation_duration = 800 + (abs(self._animation_total_distance) / 360) * 400

        if not self._is_animating:
            self._is_animating = True
            self._animation_timer.start(50)  # 50ms = ~20 FPS

    def paintEvent(self, _: QEvent) -> None:
        """Render the wheel widget with maintained aspect ratio."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.renderer.isValid():
            # Calculate square area maintaining aspect ratio
            widget_width = self.width()
            widget_height = self.height()

            # Use the smaller dimension to create a square
            size = min(widget_width, widget_height)

            # Center the square in the widget
            x = (widget_width - size) // 2
            y = (widget_height - size) // 2

            # Render SVG in the square area
            self.renderer.render(painter, QRectF(x, y, size, size))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse clicks to select slots."""
        slot_idx = self._get_slot_at_position(event.position().x(), event.position().y())
        self.log.debug("Clicked on slot %s", slot_idx)
        if slot_idx in self.slots:
            self.selected_slot = slot_idx

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse movement for hover effects."""
        slot_idx = self._get_slot_at_position(event.position().x(), event.position().y())

        if slot_idx != self._hovered_slot:
            self._hovered_slot = slot_idx
            self.update_svg()

            # Set tooltip
            if slot_idx in self.slots:
                label = self.get_slot_label(slot_idx)
                self.setToolTip(f"{label}")
            else:
                self.setToolTip("")

    def leaveEvent(self, _: QEvent) -> None:
        """Handle mouse leaving the widget."""
        # if self._hovered_member >= self._start_index:
        self._hovered_slot = self._start_index - 1
        self.update_svg()
        self.setToolTip("")

    def _get_slot_at_position(self, x: float, y: float) -> int:
        """Get the slot position at the given widget coordinates, returns 0 if none."""
        # Convert to SVG coordinates
        widget_width = self.width()
        widget_height = self.height()
        size = min(widget_width, widget_height)
        offset_x = (widget_width - size) // 2
        offset_y = (widget_height - size) // 2

        # Map click to SVG coordinate system (200x200 viewBox)
        if size > 0:
            svg_x = (x - offset_x) / size * 200
            svg_y = (y - offset_y) / size * 200

            # Check if position is within any member (only stored positions have members)
            for (
                member_x,
                member_y,
                member_radius,
                member_position,
            ) in self.slot_positions:
                distance = ((svg_x - member_x) ** 2 + (svg_y - member_y) ** 2) ** 0.5
                if distance <= member_radius + 5:  # Add some tolerance
                    return member_position

        return 0

    def _compute_slot_radius(self) -> float:
        """Calculate optimal slot size based on number of slots and desired spacing."""
        if self._num_slots <= 1:
            return 15.0  # Default for single or no slots

        # Calculate circumference and available space per slot
        circumference = 2 * math.pi * self.orbit_radius
        space_per_slot = circumference / self._num_slots

        # Reserve space for spacing, use the rest for the member size (diameter)
        available_diameter = space_per_slot - self.desired_spacing
        radius = available_diameter / 2

        # Clamp to reasonable bounds (min 3, max 20)
        return max(3.0, min(20.0, radius))

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-appropriate colors for the wheel."""
        palette = self.palette()

        # Get base colors from theme
        button_color = palette.color(QPalette.ColorRole.Button)
        # text_color = palette.color(QPalette.ColorRole.Text)

        return {
            "wheel_light": button_color.lighter(110).name(),
            "wheel_base": button_color.name(),
            "wheel_dark": button_color.darker(120).name(),
            "wheel_stroke": button_color.darker(60).name(),
        }

    def _nearest_top_slot(self) -> int:
        """Return the slot whose angle is closest to the 12 o'clock cutout."""
        if self._num_slots <= 0:
            return self._start_index

        step = 360.0 / self._num_slots
        target = 270.0  # top (because of the -90° shift in current_angle)

        def ang_err(a: float, b: float) -> float:
            # smallest signed distance a->b in degrees, then abs
            return abs(((a - b + 180.0) % 360.0) - 180.0)

        best_slot = self.slots[0]
        best_err = float("inf")

        for slot_idx in self.slots:
            base = step * self._normalized_index(slot_idx)
            current = (base + self.angle_offset - 90.0) % 360.0
            err = ang_err(current, target)
            # Stable tie-breaker: prefer pending target, else lower index
            if err < best_err or (err == best_err and slot_idx == (self._pending_slot or best_slot)):
                best_err = err
                best_slot = slot_idx

        return best_slot


# Demo code - runs when script is executed directly
if __name__ == "__main__":
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QStyle,
        QVBoxLayout,
        QWidget,
    )

    class WheelGraphicDemo(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("WheelWidget Demo - Auto-Sizing with Spacing Control")
            self.setGeometry(100, 100, 600, 400)

            # Create main widget and layout
            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            layout = QVBoxLayout(main_widget)

            # Create test members with specific hues that match their names - sparse placement (1-based)
            members = {
                1: "Red",  # Position 1
                3: "Green",  # Position 3 (skip 2)
                4: "Blue",  # Position 4
                5: "Yellow",  # Position 5
                7: "Purple",  # Position 7 (skip 6)
            }

            # Create hue mapping
            hue_mapping = {
                "Red": 0,  # Pure red
                "Green": 120,  # Pure green
                "Blue": 240,  # Pure blue
                "Yellow": 60,  # Pure yellow
                "Purple": 300,  # Purple/magenta
            }

            self.wheel = WheelGraphic(7, members, hue_mapping)
            self.wheel.selected_changed.connect(self.on_slot_changed)

            # Create controls
            prev_btn = QPushButton("◀")
            prev_btn.setToolTip("Spin left")
            prev_btn.clicked.connect(self.wheel.step_to_next)

            next_btn = QPushButton("▶")
            next_btn.setToolTip("Spin right")
            next_btn.clicked.connect(self.wheel.step_to_previous)

            reset_btn = QPushButton("⟳")
            reset_btn.setToolTip("Reset wheel rotation")
            reset_btn.clicked.connect(self.wheel.reset_rotation)

            controls_layout = QVBoxLayout()
            controls_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            back_forth_layout = QHBoxLayout()

            back_forth_layout.addWidget(prev_btn)
            back_forth_layout.addStretch()
            back_forth_layout.addWidget(next_btn)

            status_layout = QHBoxLayout()
            self.status_label = QLabel("Hover over circles to see labels, click to select")
            status_layout.addWidget(self.status_label)
            status_layout.addStretch()
            status_layout.addWidget(reset_btn)

            controls_layout.addLayout(back_forth_layout)
            controls_layout.addLayout(status_layout)

            # Add to main layout
            layout.addWidget(self.wheel)
            layout.addLayout(controls_layout)

        def on_slot_changed(self, slot_index: int) -> None:
            """Handle member selection."""
            member_label = self.wheel.get_selected_slot_label()
            if member_label:
                hue = self.wheel.hue_mapping.get(member_label, self.wheel.default_hue)
                self.status_label.setText(f"Selected: {member_label} (position {slot_index}, hue {hue:.0f}°")
            else:
                self.status_label.setText("Hover over circles to see labels, click to select")

    # Run the demo
    app = QApplication(sys.argv)
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
    demo = WheelGraphicDemo()
    demo.show()
    sys.exit(app.exec())

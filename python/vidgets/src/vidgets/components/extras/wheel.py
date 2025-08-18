from collections.abc import Mapping
import math
import colorsys
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QRectF, QTimer, Signal, QEasingCurve
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer


class WheelWidget(QWidget):
    """A refined wheel widget with predefined members and no dynamic addition/removal"""

    active_changed = Signal(int)  # Emits the position

    def __init__(
        self,
        num_slots: int,
        members: dict[int, str] | None = None,
        hue_mapping: Mapping[str, float | int] | None = None,
        parent: QWidget | None = None,
    ):
        """Initialize the wheel widget

        Args:
            num_slots: Total number of slots on the wheel
            members: Dictionary mapping position -> label string
            hue_mapping: Dictionary mapping label -> hue value (0-360). Defaults to grey if not found.
            parent: Parent widget
        """
        super().__init__(parent)
        self.setMinimumSize(200, 200)

        # Validate member positions
        if members is None:
            members = {}
        if hue_mapping is None:
            hue_mapping = {}

        for position in members:
            if not (0 <= position < num_slots):
                raise ValueError(f"Member position {position} must be within 0 to {num_slots - 1}")

        # Core widget data (public)
        self.num_slots = num_slots
        self.members = members  # Dict[int, str] - position -> label
        self.hue_mapping = hue_mapping  # Dict[str, float] - label -> hue
        self.default_hue = 0  # Grey for unmapped labels
        self.orbit_radius = 40
        self.desired_spacing = 4.0  # Desired spacing between members in SVG units

        # Display and rendering (public/internal)
        self.renderer = QSvgRenderer()
        self.member_positions = []  # Will store (x, y, radius, member_index) tuples for click detection

        # Rotation state (public)
        self.angle_offset = 0

        # Animation system (private - internal implementation details)
        self._target_angle = 0
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate_step)
        self._is_animating = False
        self._animation_start_angle = 0
        self._animation_total_distance = 0
        self._animation_duration = 1000  # milliseconds
        self._animation_elapsed = 0
        self._easing_curve = QEasingCurve(QEasingCurve.Type.InOutCubic)

        # User interaction state (private - UI tracking)
        self._active_member = -1  # Track which is currently active
        self._hovered_member = -1

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        self.update_svg()

    def _calculate_member_size(self) -> float:
        """Calculate optimal member size based on number of slots and desired spacing"""
        if self.num_slots <= 1:
            return 15.0  # Default for single or no slots

        # Calculate circumference and available space per slot
        circumference = 2 * math.pi * self.orbit_radius
        space_per_slot = circumference / self.num_slots

        # Reserve space for spacing, use the rest for the member size (diameter)
        available_diameter = space_per_slot - self.desired_spacing
        radius = available_diameter / 2

        # Clamp to reasonable bounds (min 3, max 20)
        return max(3.0, min(20.0, radius))

    @property
    def member_size(self) -> float:
        """Get the automatically calculated member size"""
        return self._calculate_member_size()

    def update_svg(self):
        """Generate SVG with members at current rotation"""
        circles = []
        center_x, center_y = 100, 100  # SVG center

        # Clear previous member positions
        self.member_positions = []
        selected_member = -1

        for i in range(self.num_slots):
            # Calculate angle for this slot (start at 12 o'clock = -90°)
            base_angle = (360 / self.num_slots) * i if self.num_slots > 0 else 0
            current_angle = base_angle + self.angle_offset - 90  # -90 to start at 12 o'clock

            # Convert to radians
            angle_rad = math.radians(current_angle)

            # Calculate position
            x = center_x + self.orbit_radius * math.cos(angle_rad)
            y = center_y + self.orbit_radius * math.sin(angle_rad)

            # Check if this slot has a member
            member = self.members.get(i)
            has_member = member is not None

            # Store position for click detection only if there's a member
            if has_member:
                self.member_positions.append((x, y, self.member_size, i))

            # Determine if this slot is at 12 o'clock (active)
            normalized_angle = (current_angle + 360) % 360
            angle_diff = min(
                abs(normalized_angle - 270), abs(normalized_angle - 270 + 360), abs(normalized_angle - 270 - 360)
            )
            is_active = angle_diff < (360 / self.num_slots / 2)  # Within half a step of 12 o'clock

            if is_active and has_member:
                selected_member = i  # Position (slot number)

            # Determine if this slot is being hovered
            is_hovered = i == self._hovered_member

            if has_member:
                # Get hue from mapping or use default (grey)
                label = member  # member is now just the label string
                hue = self.hue_mapping.get(label, self.default_hue)

                # Use member's hue for color - convert HSL to RGB for better compatibility
                h = hue / 360.0
                s = 0.7  # 70% saturation
                lightness = 0.6  # 60% lightness
                r, g, b = colorsys.hls_to_rgb(h, lightness, s)
                stroke_color = f"rgb({int(r * 255)}, {int(g * 255)}, {int(b * 255)})"

                # Set visual properties based on state
                if is_active:
                    # Active: filled circle with full opacity
                    fill_color = stroke_color
                    stroke_opacity = 1.0
                    stroke_width = 2
                else:
                    # Inactive: only stroke, no fill
                    fill_color = "none"
                    stroke_opacity = 1.0 if is_hovered else 0.75
                    stroke_width = 2
            else:
                # Empty slot: transparent with very dim stroke
                fill_color = "none"
                stroke_color = "#999"
                stroke_opacity = 0.2
                stroke_width = 1

            # Add circle (no text labels anymore - will use tooltips)
            circles.append(f'''
                <circle cx="{x:.1f}" cy="{y:.1f}" r="{self.member_size:.1f}"
                        fill="{fill_color}" stroke="{stroke_color}"
                        stroke-width="{stroke_width}" stroke-opacity="{stroke_opacity}"/>
            ''')

        svg_data = f"""
        <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <!-- Central point -->
            <circle cx="100" cy="100" r="3" fill="#333" opacity="0.7"/>

            <!-- Member circles -->
            {"".join(circles)}

            <!-- Info text -->
            <text x="100" y="25" text-anchor="middle" font-size="12" fill="#333">
                {self.num_slots} slots, {len(self.members)} members, {self.angle_offset}°
            </text>
        </svg>
        """

        self.renderer.load(svg_data.encode("utf-8"))
        self.update()

        # Emit signal if active member changed
        if selected_member != self._active_member:
            self._active_member = selected_member
            if selected_member >= 0:  # Only emit if we have a valid active member
                self.active_changed.emit(selected_member)

    def get_active_member(self):
        """Get the currently active member position (0-based slot index), returns -1 if none"""
        return self._active_member

    def get_active_member_label(self):
        """Get the currently active member label, returns None if none"""
        if 0 <= self._active_member < self.num_slots and self._active_member in self.members:
            return self.members[self._active_member]
        return None

    def set_active(self, position):
        """Rotate to make the specified position active at 12 o'clock (shortest path)"""
        self._rotate_to_position(position, clockwise=None)

    def step_to_next(self):
        """Rotate clockwise to put the next member at 12 o'clock position"""
        if len(self.members) > 1:
            current_position = self.get_active_member()

            # Get all member positions in reverse sorted order for clockwise visual rotation
            member_positions = sorted(self.members.keys(), reverse=True)

            if current_position >= 0 and current_position in member_positions:
                # Find current position in the list
                current_index = member_positions.index(current_position)
                # Get next position for clockwise visual rotation
                next_index = (current_index + 1) % len(member_positions)
                next_position = member_positions[next_index]
                self._rotate_to_position(next_position, clockwise=True)
            else:
                # If no active member, go to first member position
                first_position = member_positions[0]
                self._rotate_to_position(first_position, clockwise=True)

    def step_to_previous(self):
        """Rotate counter-clockwise to put the previous member at 12 o'clock position"""
        if len(self.members) > 1:
            current_position = self.get_active_member()

            # Get all member positions in normal sorted order for counter-clockwise visual rotation
            member_positions = sorted(self.members.keys())

            if current_position >= 0 and current_position in member_positions:
                # Find current position in the list
                current_index = member_positions.index(current_position)
                # Get next position for counter-clockwise visual rotation
                next_index = (current_index + 1) % len(member_positions)
                next_position = member_positions[next_index]
                self._rotate_to_position(next_position, clockwise=False)
            else:
                # If no active member, go to first member position
                first_position = member_positions[0]
                self._rotate_to_position(first_position, clockwise=False)

    def reset_rotation(self):
        """Reset rotation to put the first member at 12 o'clock"""
        if self.members:
            first_position = min(self.members.keys())
            self.set_active(first_position)

    def _animate_step(self):
        """Animation step with Qt easing curve transition"""
        self._animation_elapsed += 50  # 50ms per frame

        if self._animation_elapsed >= self._animation_duration:
            # Animation complete
            self.angle_offset = self._target_angle
            self._animation_timer.stop()
            self._is_animating = False
        else:
            # Calculate progress (0.0 to 1.0)
            progress = self._animation_elapsed / self._animation_duration

            # Apply Qt easing curve
            eased_progress = self._easing_curve.valueForProgress(progress)

            # Calculate current angle based on eased progress
            angle_traveled = self._animation_total_distance * eased_progress
            self.angle_offset = (self._animation_start_angle + angle_traveled) % 360

        self.update_svg()

    def _rotate_to_position(self, position, clockwise=None):
        """Start animation to target position with easing

        Args:
            position: The position to rotate to (0 to num_slots-1)
            clockwise: Direction to rotate. If None, uses shortest path.
                      If True, forces clockwise rotation.
                      If False, forces counter-clockwise rotation.
        """
        if not (0 <= position < self.num_slots):
            return

        # Calculate the angle needed to move this position to 12 o'clock
        position_base_angle = (360 / self.num_slots) * position
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

    def paintEvent(self, event):
        """Render the wheel widget with maintained aspect ratio"""
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

    def mousePressEvent(self, event):
        """Handle mouse clicks to select members"""
        member_position = self._get_member_at_position(event.position().x(), event.position().y())
        if member_position >= 0:
            self.set_active(member_position)

    def mouseMoveEvent(self, event):
        """Handle mouse movement for hover effects"""
        member_position = self._get_member_at_position(event.position().x(), event.position().y())

        if member_position != self._hovered_member:
            self._hovered_member = member_position
            self.update_svg()

            # Set tooltip
            if member_position >= 0 and member_position in self.members:
                label = self.members[member_position]
                self.setToolTip(f"{label}")
            else:
                self.setToolTip("")

    def leaveEvent(self, event):
        """Handle mouse leaving the widget"""
        if self._hovered_member >= 0:
            self._hovered_member = -1
            self.update_svg()
            self.setToolTip("")

    def _get_member_at_position(self, x, y):
        """Get the member position at the given widget coordinates, returns -1 if none"""
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
            for member_x, member_y, member_radius, member_position in self.member_positions:
                distance = ((svg_x - member_x) ** 2 + (svg_y - member_y) ** 2) ** 0.5
                if distance <= member_radius + 5:  # Add some tolerance
                    return member_position

        return -1


# Demo code - runs when script is executed directly
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QVBoxLayout,
        QHBoxLayout,
        QWidget,
        QPushButton,
        QSpinBox,
        QLabel,
    )

    class WheelDemo(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("WheelWidget Demo - Auto-Sizing with Spacing Control")
            self.setGeometry(100, 100, 600, 400)

            # Create main widget and layout
            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            layout = QVBoxLayout(main_widget)

            # Create test members with specific hues that match their names - sparse placement
            members = {
                0: "Red",  # Position 0
                2: "Green",  # Position 2 (skip 1)
                3: "Blue",  # Position 3
                6: "Yellow",  # Position 6 (skip 4, 5)
                7: "Purple",  # Position 7
            }

            # Create hue mapping
            hue_mapping = {
                "Red": 0,  # Pure red
                "Green": 120,  # Pure green
                "Blue": 240,  # Pure blue
                "Yellow": 60,  # Pure yellow
                "Purple": 300,  # Purple/magenta
            }

            # Create the wheel widget with 8 slots, 5 members, and hue mapping
            self.wheel = WheelWidget(8, members, hue_mapping)
            self.wheel.active_changed.connect(self.on_member_changed)

            # Create controls
            controls_layout = QHBoxLayout()

            # Spacing control (affects auto-calculated member size)
            spacing_label = QLabel("Spacing:")
            self.spacing_spinbox = QSpinBox()
            self.spacing_spinbox.setRange(1, 10)
            self.spacing_spinbox.setValue(2)
            self.spacing_spinbox.valueChanged.connect(self.on_spacing_changed)

            # Navigation buttons
            prev_btn = QPushButton("Previous")
            next_btn = QPushButton("Next")
            reset_btn = QPushButton("Reset")

            prev_btn.clicked.connect(self.wheel.step_to_previous)
            next_btn.clicked.connect(self.wheel.step_to_next)
            reset_btn.clicked.connect(self.wheel.reset_rotation)

            controls_layout.addWidget(spacing_label)
            controls_layout.addWidget(self.spacing_spinbox)
            controls_layout.addStretch()
            controls_layout.addWidget(prev_btn)
            controls_layout.addWidget(next_btn)
            controls_layout.addWidget(reset_btn)

            # Status label
            self.status_label = QLabel("Hover over circles to see labels, click to select")

            # Add to main layout
            layout.addWidget(self.wheel)
            layout.addLayout(controls_layout)
            layout.addWidget(self.status_label)

        def on_member_changed(self, member_position):
            """Handle member selection"""
            member_label = self.wheel.get_active_member_label()
            if member_label:
                hue = self.wheel.hue_mapping.get(member_label, self.wheel.default_hue)
                size = self.wheel.member_size
                self.status_label.setText(
                    f"Selected: {member_label} (position {member_position}, hue {hue:.0f}°, size {size:.1f})"
                )
            else:
                self.status_label.setText("Hover over circles to see labels, click to select")

        def on_spacing_changed(self, spacing):
            """Handle spacing change - updates member size automatically"""
            self.wheel.desired_spacing = float(spacing)
            self.wheel.update_svg()  # Refresh to recalculate member sizes

    # Run the demo
    app = QApplication(sys.argv)
    demo = WheelDemo()
    demo.show()
    sys.exit(app.exec())

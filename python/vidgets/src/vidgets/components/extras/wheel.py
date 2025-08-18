from collections.abc import Mapping
import math
import colorsys
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QRectF, QTimer, Signal, QEasingCurve
from PySide6.QtGui import QPainter, QPalette
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
            members: Dictionary mapping position -> label string (1-based indexing)
            hue_mapping: Dictionary mapping label -> hue value (0-360). Defaults to grey if not found.
            parent: Parent widget
        """
        super().__init__(parent)
        self.setMinimumSize(200, 200)

        # Validate member positions (1-based indexing)
        if members is None:
            members = {}
        if hue_mapping is None:
            hue_mapping = {}

        for position in members:
            if not (1 <= position <= num_slots):
                raise ValueError(f"Member position {position} must be within 1 to {num_slots} (1-based indexing)")

        # Core widget data
        self.num_slots = num_slots
        self.members = members  # position -> label
        self.hue_mapping = hue_mapping
        self.default_hue = 0  # Grey for unmapped labels
        self.orbit_radius = 60
        self.desired_spacing = 12.0  # Desired spacing between members in SVG units
        self.show_info_text = False

        # Display and rendering
        self.renderer = QSvgRenderer()
        self.member_positions: list[
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
        self._active_member = 0  # Track which is currently active (0 means none)
        self._hovered_member = 0  # 0 means none

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

    def _get_theme_colors(self):
        """Get theme-appropriate colors for the wheel"""
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

    def update_svg(self):
        """Generate SVG with members at current rotation"""
        circles = []
        center_x, center_y = 100, 100  # SVG center

        # Get theme colors
        colors = self._get_theme_colors()

        # Get text color from theme
        text_color = self.palette().color(QPalette.ColorRole.Text).name()

        # Clear previous member positions
        self.member_positions = []
        selected_member = 0  # 0 means no member selected

        for i in range(1, self.num_slots + 1):  # 1-based indexing
            # Calculate angle for this slot (start at 12 o'clock = -90°)
            # Subtract 1 from i for angle calculation since angles are 0-based
            base_angle = (360 / self.num_slots) * (i - 1) if self.num_slots > 0 else 0
            current_angle = base_angle + self.angle_offset - 90  # -90 to start at 12 o'clock

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
            is_active = angle_diff < (360 / self.num_slots / 4)  # Within a quarter of a step of 12 o'clock

            if is_active and has_member:
                selected_member = i  # Position (slot number, 1-based)

            is_hovered = i == self._hovered_member

            if has_member:
                label = member
                hue = self.hue_mapping.get(label, self.default_hue)

                h = hue / 360.0
                s = 0.7
                lightness = 0.6
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
                    stroke_opacity = 1.0 if is_hovered else 0.5
                    stroke_width = 2
            else:
                # Empty slot: transparent with very dim stroke using theme color
                fill_color = "none"
                stroke_color = colors["wheel_stroke"]
                stroke_opacity = 0.5
                stroke_width = 1

            circles.append(f'''
                <circle
                    cx="{x:.1f}" cy="{y:.1f}" r="{self.member_size:.1f}"
                    fill="{fill_color}" stroke="{stroke_color}"
                    stroke-width="{stroke_width}" stroke-opacity="{stroke_opacity}"
                />
            ''')

        # Calculate the outer wheel radius and cutout properties
        wheel_outer_radius = self.orbit_radius + self.member_size * 1.5  # Wheel extends beyond member orbit
        wheel_inner_radius = 10  # Inner hole radius
        cutout_radius = self.member_size + self.desired_spacing / 2  # Active Cutout slightly larger than member circles
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
                {self.num_slots} slots, {len(self.members)} members, {self.angle_offset}°
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

        # Emit signal if active member changed
        if selected_member != self._active_member:
            self._active_member = selected_member
            if selected_member > 0:  # Only emit if we have a valid active member (1-based)
                self.active_changed.emit(selected_member)

    def get_active_member(self):
        """Get the currently active member position (1-based slot index), returns 0 if none"""
        return self._active_member

    def get_active_member_label(self):
        """Get the currently active member label, returns None if none"""
        if self._active_member > 0 and self._active_member in self.members:
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

            if current_position > 0 and current_position in member_positions:
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

            if current_position > 0 and current_position in member_positions:
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
            position: The position to rotate to (1 to num_slots)
            clockwise: Direction to rotate. If None, uses shortest path.
                      If True, forces clockwise rotation.
                      If False, forces counter-clockwise rotation.
        """
        if not (1 <= position <= self.num_slots):
            return

        # Calculate the angle needed to move this position to 12 o'clock
        # Convert 1-based position to 0-based for angle calculation
        position_base_angle = (360 / self.num_slots) * (position - 1)
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
        if member_position > 0:
            self.set_active(member_position)

    def mouseMoveEvent(self, event):
        """Handle mouse movement for hover effects"""
        member_position = self._get_member_at_position(event.position().x(), event.position().y())

        if member_position != self._hovered_member:
            self._hovered_member = member_position
            self.update_svg()

            # Set tooltip
            if member_position > 0 and member_position in self.members:
                label = self.members[member_position]
                self.setToolTip(f"{label}")
            else:
                self.setToolTip("")

    def leaveEvent(self, event):
        """Handle mouse leaving the widget"""
        if self._hovered_member > 0:
            self._hovered_member = 0
            self.update_svg()
            self.setToolTip("")

    def _get_member_at_position(self, x, y):
        """Get the member position at the given widget coordinates, returns 0 if none"""
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

        return 0


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
        QLabel,
        QStyle,
    )
    from PySide6.QtCore import Qt

    class WheelDemo(QMainWindow):
        def __init__(self):
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

            self.wheel = WheelWidget(7, members, hue_mapping)
            self.wheel.active_changed.connect(self.on_member_changed)

            # Create controls
            prev_btn = QPushButton("◀")
            prev_btn.setToolTip("Previous member")
            prev_btn.clicked.connect(self.wheel.step_to_previous)

            next_btn = QPushButton("▶")
            next_btn.setToolTip("Next member")
            next_btn.clicked.connect(self.wheel.step_to_next)

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

        def on_member_changed(self, member_position):
            """Handle member selection"""
            member_label = self.wheel.get_active_member_label()
            if member_label:
                hue = self.wheel.hue_mapping.get(member_label, self.wheel.default_hue)
                self.status_label.setText(f"Selected: {member_label} (position {member_position}, hue {hue:.0f}°")
            else:
                self.status_label.setText("Hover over circles to see labels, click to select")

    # Run the demo
    app = QApplication(sys.argv)
    app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
    demo = WheelDemo()
    demo.show()
    sys.exit(app.exec())

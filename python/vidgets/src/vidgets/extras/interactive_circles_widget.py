import math

from PySide6.QtCore import QRectF, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget


class InteractiveCirclesWidget(QWidget):
    """Interactive circles with manual control over count, size, and rotation."""

    # Signal emitted when the active circle changes
    active_circle_changed = Signal(int)  # Emits the 1-based circle number

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)

        self.num_circles = 5  # Start with 5 circles
        self.angle_offset = 0  # Manual rotation angle
        self.target_angle = 0  # Target angle for animation
        self.orbit_radius = 40
        self.renderer = QSvgRenderer()

        # Store circle positions for click detection
        self.circle_positions = []  # Will store (x, y, circle_index) tuples
        self._previous_active_circle = -1  # Track which circle was previously active

        # Animation timer
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_step)
        self.animation_speed = 5  # degrees per frame
        self.is_animating = False

        self.update_svg()

    def calculate_circle_size(self):
        """Auto-compute circle size based on number of circles."""
        # More circles = smaller circles to avoid overlap
        # Formula: base size inversely proportional to sqrt of count
        base_size = 12
        size_factor = math.sqrt(max(1, self.num_circles / 3))
        return max(3, min(15, base_size / size_factor))

    def update_svg(self):
        """Generate SVG with circles at current rotation."""
        circles = []
        center_x, center_y = 100, 100  # SVG center
        circle_size = self.calculate_circle_size()

        # Clear previous circle positions
        self.circle_positions = []
        current_active_circle = -1

        for i in range(self.num_circles):
            # Calculate angle for this circle (start at 12 o'clock = -90°)
            base_angle = (360 / self.num_circles) * i if self.num_circles > 0 else 0
            current_angle = base_angle + self.angle_offset - 90  # -90 to start at 12 o'clock

            # Convert to radians
            angle_rad = math.radians(current_angle)

            # Calculate position
            x = center_x + self.orbit_radius * math.cos(angle_rad)
            y = center_y + self.orbit_radius * math.sin(angle_rad)

            # Store circle position for click detection (SVG coordinates)
            self.circle_positions.append((x, y, circle_size, i))

            # Determine if this circle is at 12 o'clock (active)
            # Normalize angle to 0-360 and check if it's close to 270° (12 o'clock in our coordinate system)
            normalized_angle = (current_angle + 360) % 360
            angle_diff = min(
                abs(normalized_angle - 270),
                abs(normalized_angle - 270 + 360),
                abs(normalized_angle - 270 - 360),
            )
            is_active = angle_diff < (360 / self.num_circles / 2)  # Within half a step of 12 o'clock

            if is_active:
                current_active_circle = i + 1  # 1-based for display

            # Set opacity based on active state
            opacity = 1.0 if is_active else 0.4
            text_opacity = 1.0 if is_active else 0.6

            # Create unique color for each circle
            hue = (i * 360 / max(1, self.num_circles)) % 360
            color = f'hsl({hue}, 70%, 60%)'

            # Add circle with varying opacity
            circles.append(f"""
                <circle cx="{x:.1f}" cy="{y:.1f}" r="{circle_size:.1f}"
                        fill="{color}" stroke="white" stroke-width="1" opacity="{opacity}"/>
                <text x="{x:.1f}" y="{y + 2:.1f}" text-anchor="middle"
                      font-size="{max(8, circle_size * 0.8):.0f}"
                      fill="white" font-weight="bold" opacity="{text_opacity}">{i + 1}</text>
            """)

        svg_data = f"""
        <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <!-- Central point -->
            <circle cx="100" cy="100" r="3" fill="#333" opacity="0.7"/>

            <!-- Revolving circles -->
            {''.join(circles)}

            <!-- Info text -->
            <text x="100" y="25" text-anchor="middle" font-size="12" fill="#333">
                {self.num_circles} circles, {self.angle_offset}°
            </text>
            <text x="100" y="185" text-anchor="middle" font-size="10" fill="#666">
                Circle size: {self.calculate_circle_size():.1f}
            </text>
        </svg>
        """

        self.renderer.load(svg_data.encode('utf-8'))
        self.update()

        # Emit signal if active circle changed
        if current_active_circle != self._previous_active_circle:
            self._previous_active_circle = current_active_circle
            if current_active_circle > 0:  # Only emit if we have a valid active circle
                self.active_circle_changed.emit(current_active_circle)

    def get_active_circle(self):
        """Get the currently active circle (1-based), returns -1 if none."""
        return self._previous_active_circle

    def add_circle(self):
        """Add a circle (max 20)."""
        if self.num_circles < 20:
            self.num_circles += 1
            self.update_svg()

    def remove_circle(self):
        """Remove a circle (min 1)."""
        if self.num_circles > 1:
            self.num_circles -= 1
            self.update_svg()

    def _animate_step(self):
        """Animation step - move towards target angle."""
        if abs(self.target_angle - self.angle_offset) < self.animation_speed:
            # Close enough, snap to target and stop
            self.angle_offset = self.target_angle
            self.animation_timer.stop()
            self.is_animating = False
        else:
            # Calculate shortest path to target
            diff = self.target_angle - self.angle_offset
            # Handle wraparound (e.g., from 350° to 10°)
            if diff > 180:
                diff -= 360
            elif diff < -180:
                diff += 360

            # Move towards target
            if diff > 0:
                self.angle_offset = (self.angle_offset + self.animation_speed) % 360
            else:
                self.angle_offset = (self.angle_offset - self.animation_speed) % 360

        self.update_svg()

    def _animate_to_angle(self, target_angle):
        """Start animation to target angle."""
        self.target_angle = target_angle % 360
        if not self.is_animating:
            self.is_animating = True
            self.animation_timer.start(50)  # 50ms = ~20 FPS

    def step_rotation(self, degrees):
        """Step the rotation by specified degrees."""
        target = (self.angle_offset + degrees) % 360
        self._animate_to_angle(target)

    def step_to_next_circle(self):
        """Rotate to put the next circle at 12 o'clock position."""
        if self.num_circles > 1:
            step_angle = 360 / self.num_circles
            target = (self.angle_offset + step_angle) % 360
            self._animate_to_angle(target)

    def step_to_previous_circle(self):
        """Rotate to put the previous circle at 12 o'clock position."""
        if self.num_circles > 1:
            step_angle = 360 / self.num_circles
            target = (self.angle_offset - step_angle) % 360
            self._animate_to_angle(target)

    def reset_rotation(self) -> None:
        """Reset rotation to 0 degrees."""
        self._animate_to_angle(0)

    def set_active_circle(self, circle_number) -> None:
        """Set the active circle by its number (1-based)."""
        if 1 <= circle_number <= self.num_circles:
            self.rotate_to_circle(circle_number - 1)  # Convert to 0-based index

    def set_circle_count(self, count) -> None:
        """Set exact circle count."""
        self.num_circles = max(1, min(20, count))
        self.update_svg()

    def paintEvent(self, _) -> None:
        """Render the interactive circles with maintained aspect ratio."""
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
        """Handle mouse clicks to select circles."""
        # Get click position
        click_x = event.position().x()
        click_y = event.position().y()

        # Convert to SVG coordinates
        widget_width = self.width()
        widget_height = self.height()
        size = min(widget_width, widget_height)
        offset_x = (widget_width - size) // 2
        offset_y = (widget_height - size) // 2

        # Map click to SVG coordinate system (200x200 viewBox)
        if size > 0:
            svg_x = (click_x - offset_x) / size * 200
            svg_y = (click_y - offset_y) / size * 200

            # Check if click is within any circle
            for circle_x, circle_y, circle_radius, circle_index in self.circle_positions:
                distance = ((svg_x - circle_x) ** 2 + (svg_y - circle_y) ** 2) ** 0.5
                if distance <= circle_radius + 5:  # Add some tolerance for easier clicking
                    self.rotate_to_circle(circle_index)
                    break

    def rotate_to_circle(self, circle_index):
        """Rotate to make the specified circle active at 12 o'clock."""
        if self.num_circles > 0:
            # Calculate the angle needed to move this circle to 12 o'clock
            circle_base_angle = (360 / self.num_circles) * circle_index
            # We want this circle at angle 0 (after the -90 offset in update_svg)
            # So target_angle_offset should be -circle_base_angle
            target_angle = (-circle_base_angle) % 360
            self._animate_to_angle(target_angle)

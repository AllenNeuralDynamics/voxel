"""SVG Rendering Examples for Qt.

This module demonstrates different approaches to rendering SVG elements in Qt applications.
"""

import math
import sys

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .interactive_circles_widget import InteractiveCirclesWidget


class SVGFromStringWidget(QWidget):
    """Render SVG from string data using QSvgRenderer and custom painting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)

        # Simple SVG circle that changes color
        self.svg_data = """
        <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="50" r="40" fill="{color}" stroke="black" stroke-width="2"/>
            <text x="50" y="55" text-anchor="middle" font-size="12" fill="white">SVG</text>
        </svg>
        """

        self.color = "#3498db"
        self.renderer = QSvgRenderer()
        self.update_svg()

        # Timer to animate color changes
        self.timer = QTimer()
        self.timer.timeout.connect(self.change_color)
        self.timer.start(2000)  # Change color every 2 seconds

    def update_svg(self):
        """Update the SVG with current color."""
        svg_string = self.svg_data.format(color=self.color)
        self.renderer.load(svg_string.encode("utf-8"))
        self.update()

    def change_color(self):
        """Cycle through different colors."""
        colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6"]
        current_index = colors.index(self.color) if self.color in colors else 0
        self.color = colors[(current_index + 1) % len(colors)]
        self.update_svg()

    def paintEvent(self, _):
        """Custom paint event to render SVG."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Render SVG centered in widget
        if self.renderer.isValid():
            size = min(self.width(), self.height()) - 20
            x = (self.width() - size) // 2
            y = (self.height() - size) // 2
            self.renderer.render(painter, QRectF(x, y, size, size))


class InteractiveSVGWidget(QWidget):
    """Interactive SVG with mouse hover effects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setMouseTracking(True)

        self.hover_x = 50
        self.hover_y = 50
        self.renderer = QSvgRenderer()
        self.update_svg()

    def update_svg(self):
        """Update SVG with hover position."""
        svg_data = f"""
        <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <radialGradient id="hoverGrad" cx="{self.hover_x}%" cy="{self.hover_y}%">
                    <stop offset="0%" stop-color="#ff6b6b" stop-opacity="0.8"/>
                    <stop offset="100%" stop-color="#4ecdc4" stop-opacity="0.2"/>
                </radialGradient>
            </defs>
            <rect width="200" height="200" fill="url(#hoverGrad)"/>
            <circle cx="{self.hover_x * 2}" cy="{self.hover_y * 2}" r="15" fill="white" opacity="0.8"/>
            <text x="100" y="190" text-anchor="middle" font-size="14" fill="black">Move mouse here</text>
        </svg>
        """
        self.renderer.load(svg_data.encode("utf-8"))
        self.update()

    def mouseMoveEvent(self, event):
        """Update hover position based on mouse (accounting for aspect ratio)."""
        widget_width = self.width()
        widget_height = self.height()

        # Calculate the square area (same as in paintEvent)
        size = min(widget_width, widget_height)
        x_offset = (widget_width - size) // 2
        y_offset = (widget_height - size) // 2

        # Get mouse position relative to the square area
        mouse_x = event.position().x() - x_offset
        mouse_y = event.position().y() - y_offset

        # Convert to percentage within the square area
        if size > 0:
            self.hover_x = min(max(mouse_x / size * 100, 0), 100)
            self.hover_y = min(max(mouse_y / size * 100, 0), 100)
        else:
            self.hover_x = 50
            self.hover_y = 50

        self.update_svg()

    def paintEvent(self, _) -> None:
        """Render the interactive SVG with maintained aspect ratio."""
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


class SVGIconWidget(QWidget):
    """Display SVG icons that can be styled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 100)

        # Different icon SVGs
        self.icons = {
            "play": """
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 5v14l11-7z" fill="{color}"/>
                </svg>
            """,
            "pause": """
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" fill="{color}"/>
                </svg>
            """,
            "stop": """
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M6 6h12v12H6z" fill="{color}"/>
                </svg>
            """,
        }

        self.current_icon = "play"
        self.color = "#2c3e50"
        self.renderer = QSvgRenderer()
        self.update_svg()

    def update_svg(self):
        """Update current icon with color."""
        svg_string = self.icons[self.current_icon].format(color=self.color)
        self.renderer.load(svg_string.encode("utf-8"))
        self.update()

    def set_icon(self, icon_name):
        """Change the displayed icon."""
        if icon_name in self.icons:
            self.current_icon = icon_name
            self.update_svg()

    def set_color(self, color):
        """Change the icon color."""
        self.color = color
        self.update_svg()

    def paintEvent(self, _) -> None:
        """Render the icon."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.renderer.isValid():
            # Center the icon
            size = min(self.width(), self.height()) - 20
            x = (self.width() - size) // 2
            y = (self.height() - size) // 2
            self.renderer.render(painter, QRectF(x, y, size, size))


class RevolvingCirclesWidget(QWidget):
    """Loading animation with n circles revolving around a central point."""

    def __init__(self, parent=None, num_circles=8, radius=30, circle_size=8):
        super().__init__(parent)
        self.setMinimumSize(200, 200)

        self.num_circles = num_circles
        self.orbit_radius = radius
        self.circle_size = circle_size
        self.angle_offset = 0
        self.renderer = QSvgRenderer()

        # Timer for smooth animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)  # Update every 50ms for smooth animation

        self.update_svg()

    def animate(self):
        """Update the rotation angle for animation."""
        max_angle = 360
        self.angle_offset += 5  # Degrees per frame
        if self.angle_offset >= max_angle:
            self.angle_offset = 0
        self.update_svg()

    def update_svg(self):
        """Generate SVG with circles at current rotation."""
        circles = []
        center_x, center_y = 100, 100  # SVG center

        for i in range(self.num_circles):
            # Calculate angle for this circle
            base_angle = (360 / self.num_circles) * i
            current_angle = base_angle + self.angle_offset

            # Convert to radians
            angle_rad = math.radians(current_angle)

            # Calculate position
            x = center_x + self.orbit_radius * math.cos(angle_rad)
            y = center_y + self.orbit_radius * math.sin(angle_rad)

            # Calculate opacity based on position (fade effect)
            # Circles at the "front" (right side) are more opaque
            opacity = 0.3 + 0.7 * (math.cos(angle_rad) + 1) / 2

            # Create circle with gradient color
            hue = (i * 360 / self.num_circles + self.angle_offset) % 360
            color = f"hsl({hue}, 70%, 60%)"

            circles.append(f"""
                <circle cx="{x:.1f}" cy="{y:.1f}" r="{self.circle_size}"
                        fill="{color}" opacity="{opacity:.2f}"/>
            """)

        svg_data = f"""
        <svg width="200" height="200" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
            <!-- Central point indicator -->
            <circle cx="100" cy="100" r="2" fill="#333" opacity="0.5"/>

            <!-- Revolving circles -->
            {"".join(circles)}

            <!-- Optional loading text -->
            <text x="100" y="170" text-anchor="middle" font-size="12" fill="#666">Loading...</text>
        </svg>
        """

        self.renderer.load(svg_data.encode("utf-8"))
        self.update()

    def set_num_circles(self, num):
        """Change the number of revolving circles."""
        self.num_circles = max(3, min(20, num))  # Limit between 3-20
        self.update_svg()

    def set_orbit_radius(self, radius) -> None:
        """Change the orbit radius."""
        self.orbit_radius = max(10, min(80, radius))  # Limit between 10-80
        self.update_svg()

    def set_circle_size(self, size) -> None:
        """Change the size of individual circles."""
        self.circle_size = max(2, min(15, size))  # Limit between 2-15
        self.update_svg()

    def start_animation(self) -> None:
        """Start the animation."""
        self.timer.start(50)

    def stop_animation(self) -> None:
        """Stop the animation."""
        self.timer.stop()

    def paintEvent(self, _) -> None:
        """Render the revolving circles with maintained aspect ratio."""
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


class SVGRenderingDemo(QMainWindow):
    """Main demo window showing different SVG rendering approaches."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVG Rendering in Qt - Examples")
        self.setGeometry(100, 100, 800, 600)
        self.setup_ui()

    def setup_ui(self) -> None:  # noqa: PLR0915
        """Setup the demo interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Title
        title = QLabel("SVG Rendering Examples in Qt")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Create vertical splitter for top and bottom rows
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(main_splitter)

        # Top row - horizontal splitter
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(top_splitter)

        # Animated SVG example
        animated_group = QGroupBox("Animated SVG (Custom Renderer)")
        animated_layout = QVBoxLayout(animated_group)
        self.animated_svg = SVGFromStringWidget()
        animated_layout.addWidget(self.animated_svg)
        top_splitter.addWidget(animated_group)

        # Interactive SVG example
        interactive_group = QGroupBox("Interactive SVG (Mouse Hover)")
        interactive_layout = QVBoxLayout(interactive_group)
        self.interactive_svg = InteractiveSVGWidget()
        interactive_layout.addWidget(self.interactive_svg)
        top_splitter.addWidget(interactive_group)

        # Bottom row - horizontal splitter
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(bottom_splitter)

        # SVG Icons example
        icons_group = QGroupBox("SVG Icons (Controllable)")
        icons_layout = QVBoxLayout(icons_group)
        self.icon_widget = SVGIconWidget()
        icons_layout.addWidget(self.icon_widget)

        # Control buttons for icons
        button_layout = QHBoxLayout()
        play_btn = QPushButton("Play")
        pause_btn = QPushButton("Pause")
        stop_btn = QPushButton("Stop")

        play_btn.clicked.connect(lambda: self.icon_widget.set_icon("play"))
        pause_btn.clicked.connect(lambda: self.icon_widget.set_icon("pause"))
        stop_btn.clicked.connect(lambda: self.icon_widget.set_icon("stop"))

        button_layout.addWidget(play_btn)
        button_layout.addWidget(pause_btn)
        button_layout.addWidget(stop_btn)
        icons_layout.addLayout(button_layout)

        # Color buttons
        color_layout = QHBoxLayout()
        red_btn = QPushButton("Red")
        blue_btn = QPushButton("Blue")
        green_btn = QPushButton("Green")

        red_btn.clicked.connect(lambda: self.icon_widget.set_color("#e74c3c"))
        blue_btn.clicked.connect(lambda: self.icon_widget.set_color("#3498db"))
        green_btn.clicked.connect(lambda: self.icon_widget.set_color("#2ecc71"))

        color_layout.addWidget(red_btn)
        color_layout.addWidget(blue_btn)
        color_layout.addWidget(green_btn)
        icons_layout.addLayout(color_layout)

        bottom_splitter.addWidget(icons_group)

        # Revolving Circles Loading Animation
        loading_group = QGroupBox("Loading Animation (Revolving Circles)")
        loading_layout = QVBoxLayout(loading_group)
        self.loading_widget = RevolvingCirclesWidget(num_circles=8, radius=35, circle_size=6)
        loading_layout.addWidget(self.loading_widget)

        # Control buttons for loading animation
        loading_controls = QHBoxLayout()

        start_btn = QPushButton("Start")
        stop_btn = QPushButton("Stop")
        circles_3_btn = QPushButton("3 Circles")
        circles_6_btn = QPushButton("6 Circles")
        circles_12_btn = QPushButton("12 Circles")

        start_btn.clicked.connect(self.loading_widget.start_animation)
        stop_btn.clicked.connect(self.loading_widget.stop_animation)
        circles_3_btn.clicked.connect(lambda: self.loading_widget.set_num_circles(3))
        circles_6_btn.clicked.connect(lambda: self.loading_widget.set_num_circles(6))
        circles_12_btn.clicked.connect(lambda: self.loading_widget.set_num_circles(12))

        loading_controls.addWidget(start_btn)
        loading_controls.addWidget(stop_btn)
        loading_controls.addWidget(circles_3_btn)
        loading_controls.addWidget(circles_6_btn)
        loading_controls.addWidget(circles_12_btn)
        loading_layout.addLayout(loading_controls)

        # Size controls
        size_controls = QHBoxLayout()
        small_radius_btn = QPushButton("Small Orbit")
        large_radius_btn = QPushButton("Large Orbit")
        small_circles_btn = QPushButton("Small Dots")
        large_circles_btn = QPushButton("Large Dots")

        small_radius_btn.clicked.connect(lambda: self.loading_widget.set_orbit_radius(25))
        large_radius_btn.clicked.connect(lambda: self.loading_widget.set_orbit_radius(45))
        small_circles_btn.clicked.connect(lambda: self.loading_widget.set_circle_size(4))
        large_circles_btn.clicked.connect(lambda: self.loading_widget.set_circle_size(10))

        size_controls.addWidget(small_radius_btn)
        size_controls.addWidget(large_radius_btn)
        size_controls.addWidget(small_circles_btn)
        size_controls.addWidget(large_circles_btn)
        loading_layout.addLayout(size_controls)

        bottom_splitter.addWidget(loading_group)

        # Interactive Circles with Manual Control
        manual_group = QGroupBox("Manual Control Circles")
        manual_layout = QVBoxLayout(manual_group)
        self.manual_circles = InteractiveCirclesWidget()
        manual_layout.addWidget(self.manual_circles)

        # Active Circle Selector
        selector_layout = QHBoxLayout()
        selector_label = QLabel("Active Circle:")
        self.circle_combo = QComboBox()
        self.circle_combo.addItems([f"Circle {i + 1}" for i in range(5)])  # Start with 5 circles
        self.circle_combo.setCurrentIndex(0)  # Default to first circle

        # Connect combobox to widget
        self.circle_combo.currentIndexChanged.connect(self._on_combo_changed)

        # Connect widget signal to combobox
        self.manual_circles.active_circle_changed.connect(self._on_active_circle_changed)

        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self.circle_combo)
        selector_layout.addStretch()  # Push elements to the left
        manual_layout.addLayout(selector_layout)

        # Circle count controls
        count_controls = QHBoxLayout()
        minus_btn = QPushButton("-")
        plus_btn = QPushButton("+")
        reset_btn = QPushButton("Reset")
        count_3_btn = QPushButton("3")
        count_8_btn = QPushButton("8")
        count_12_btn = QPushButton("12")

        minus_btn.clicked.connect(self.manual_circles.remove_circle)
        plus_btn.clicked.connect(self.manual_circles.add_circle)
        reset_btn.clicked.connect(lambda: self.manual_circles.set_circle_count(5))
        count_3_btn.clicked.connect(lambda: self.manual_circles.set_circle_count(3))
        count_8_btn.clicked.connect(lambda: self.manual_circles.set_circle_count(8))
        count_12_btn.clicked.connect(lambda: self.manual_circles.set_circle_count(12))

        count_controls.addWidget(minus_btn)
        count_controls.addWidget(plus_btn)
        count_controls.addWidget(reset_btn)
        count_controls.addWidget(count_3_btn)
        count_controls.addWidget(count_8_btn)
        count_controls.addWidget(count_12_btn)
        manual_layout.addLayout(count_controls)

        # Rotation controls
        rotation_controls = QHBoxLayout()
        prev_circle_btn = QPushButton("◀ Prev Circle")
        next_circle_btn = QPushButton("Next Circle ▶")
        reset_rotation_btn = QPushButton("Reset 0°")
        step_back_btn = QPushButton("↶ 15°")
        step_fwd_btn = QPushButton("15° ↷")

        prev_circle_btn.clicked.connect(self.manual_circles.step_to_previous_circle)
        next_circle_btn.clicked.connect(self.manual_circles.step_to_next_circle)
        reset_rotation_btn.clicked.connect(self.manual_circles.reset_rotation)
        step_back_btn.clicked.connect(lambda: self.manual_circles.step_rotation(-15))
        step_fwd_btn.clicked.connect(lambda: self.manual_circles.step_rotation(15))

        rotation_controls.addWidget(prev_circle_btn)
        rotation_controls.addWidget(next_circle_btn)
        rotation_controls.addWidget(reset_rotation_btn)
        rotation_controls.addWidget(step_back_btn)
        rotation_controls.addWidget(step_fwd_btn)
        manual_layout.addLayout(rotation_controls)

        bottom_splitter.addWidget(manual_group)

        # Set equal sizes for all panels
        top_splitter.setSizes([400, 400])
        bottom_splitter.setSizes([270, 270, 270])  # Three panels in bottom row
        main_splitter.setSizes([300, 400])

        # Override circle count methods to update combobox
        original_add = self.manual_circles.add_circle
        original_remove = self.manual_circles.remove_circle
        original_set_count = self.manual_circles.set_circle_count

        def update_combo_for_add():
            original_add()
            self._update_combo_items()

        def update_combo_for_remove():
            original_remove()
            self._update_combo_items()

        def update_combo_for_set(count):
            original_set_count(count)
            self._update_combo_items()

        # Replace methods with versions that update combobox
        self.manual_circles.add_circle = update_combo_for_add
        self.manual_circles.remove_circle = update_combo_for_remove
        self.manual_circles.set_circle_count = update_combo_for_set

    def _on_combo_changed(self, index):
        """Handle combobox selection change."""
        circle_number = index + 1  # Convert to 1-based
        self.manual_circles.set_active_circle(circle_number)

    def _on_active_circle_changed(self, circle_number):
        """Handle active circle change from widget."""
        # Block signals to prevent recursion
        self.circle_combo.blockSignals(True)
        self.circle_combo.setCurrentIndex(circle_number - 1)  # Convert to 0-based
        self.circle_combo.blockSignals(False)

    def _update_combo_items(self):
        """Update combobox items when circle count changes."""
        current_count = self.manual_circles.num_circles
        current_active = self.manual_circles.get_active_circle()

        # Block signals during update
        self.circle_combo.blockSignals(True)

        # Clear and repopulate
        self.circle_combo.clear()
        self.circle_combo.addItems([f"Circle {i + 1}" for i in range(current_count)])

        # Restore selection if valid
        if 1 <= current_active <= current_count:
            self.circle_combo.setCurrentIndex(current_active - 1)
        elif current_count > 0:
            self.circle_combo.setCurrentIndex(0)
        block_signals = False
        self.circle_combo.blockSignals(block_signals)


def main():
    """Run the SVG rendering demo."""
    app = QApplication(sys.argv)

    # Create and show the demo window
    demo = SVGRenderingDemo()
    demo.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

from datetime import UTC, datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget
from vxl_qt.ui.kit import Text


class SlidingDrawer(QWidget):
    """A sliding drawer widget that can be toggled from the right side."""

    def __init__(self, parent=None, width=350):
        super().__init__(parent)
        self.drawer_width = width
        self.is_open = False

        # Set up the drawer widget
        self.setFixedWidth(width)
        self.setStyleSheet("""
            SlidingDrawer {
                border-left: 1px solid palette(mid);
                border-top: 1px solid palette(mid);
                border-bottom: 1px solid palette(mid);
            }
        """)

        # Create layout for drawer content
        drawer_layout = QVBoxLayout(self)
        drawer_layout.setContentsMargins(12, 12, 12, 12)

        # Create simple header (no close button)
        self.title_label = Text.section("Event Log")

        drawer_layout.addWidget(self.title_label)

        # Create the log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            QTextEdit {
                border: 1px solid palette(mid);
                border-radius: 4px;
                padding: 8px;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
            QScrollBar:vertical {
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: palette(button);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: palette(highlight);
            }
        """)
        drawer_layout.addWidget(self.log_display)

        # Initially hide the drawer
        self.hide()

        # Animation for sliding
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def add_log_message(self, message: str):
        """Add a message to the log display."""
        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_display.append(log_entry)

    def toggle(self):
        """Toggle the drawer open/closed."""
        parent_widget = self.parent()
        if not parent_widget or not isinstance(parent_widget, QWidget):
            return

        self.animation.finished.connect(self.hide)

        if self.is_open:
            # Close the drawer (slide out to the right)
            start_rect = self.geometry()
            end_rect = start_rect.translated(self.drawer_width, 0)
            self.animation.setStartValue(start_rect)
            self.animation.setEndValue(end_rect)
            self.is_open = False
        else:
            self.animation.finished.disconnect()
            # Open the drawer (slide in from the right)
            self.show()
            parent_rect = parent_widget.rect()
            start_x = parent_rect.width()
            end_x = parent_rect.width() - self.drawer_width

            # Position drawer below the header (leave space for the checkbox)
            header_height = 40  # Height of header area with checkbox
            drawer_y = header_height
            drawer_height = parent_rect.height() - header_height

            # Position drawer to not cover the header
            self.setGeometry(start_x, drawer_y, self.drawer_width, drawer_height)
            end_geometry = self.geometry()
            end_geometry.moveLeft(end_x)

            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(end_geometry)
            self.is_open = True  # Update state for opening

        self.animation.start()

    def resizeEvent(self, a0):
        """Handle parent resize to keep drawer positioned correctly."""
        super().resizeEvent(a0)
        parent_widget = self.parent()
        if parent_widget and isinstance(parent_widget, QWidget) and self.is_open:
            parent_rect = parent_widget.rect()
            header_height = 40  # Same as in toggle method
            new_geometry = self.geometry()
            new_geometry.moveLeft(parent_rect.width() - self.drawer_width)
            new_geometry.setTop(header_height)
            new_geometry.setHeight(parent_rect.height() - header_height)
            self.setGeometry(new_geometry)

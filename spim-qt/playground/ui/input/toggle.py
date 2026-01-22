"""VToggle - An animated toggle switch component for the Voxel library.

Based on the PySide6 animated widgets tutorial:
https://www.pythonguis.com/tutorials/PySide6-animated-widgets/
"""

import logging
from collections.abc import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QCheckBox, QSizePolicy, QVBoxLayout, QWidget


class _AnimatedToggle(QCheckBox):
    """An animated toggle switch component that provides a smooth, animated alternative to QCheckBox.

    Features:
    - Smooth sliding animation with customizable easing
    - Pulse effect on state change
    - Customizable colors for different states
    - Drop-in replacement for QCheckBox
    - Theme-aware default colors

    Note: This is a private implementation class. Use VToggle instead.
    """

    _transparent_pen = QPen(Qt.GlobalColor.transparent)
    _light_grey_pen = QPen(Qt.GlobalColor.lightGray)

    def __init__(
        self,
        parent: QWidget | None = None,
        bar_color: Qt.GlobalColor | str = Qt.GlobalColor.gray,
        checked_color: str = "#0078D4",  # Microsoft blue
        handle_color: Qt.GlobalColor = Qt.GlobalColor.white,
        pulse_unchecked_color: str = "#44999999",
        pulse_checked_color: str = "#440078D4",
    ):
        """Initialize the VToggle component.

        Args:
            parent: Parent widget
            bar_color: Color of the toggle bar when unchecked
            checked_color: Color of the toggle bar and handle when checked
            handle_color: Color of the toggle handle when unchecked
            pulse_unchecked_color: Color of the pulse effect when unchecked
            pulse_checked_color: Color of the pulse effect when checked

        """
        super().__init__(parent)

        # Save our properties on the object via self, so we can access them later
        # in the paintEvent.
        self._bar_brush = QBrush(bar_color)
        self._bar_checked_brush = QBrush(QColor(checked_color).lighter())

        self._handle_brush = QBrush(handle_color)
        self._handle_checked_brush = QBrush(QColor(checked_color))

        self._pulse_unchecked_animation = QBrush(QColor(pulse_unchecked_color))
        self._pulse_checked_animation = QBrush(QColor(pulse_checked_color))

        # Setup the rest of the widget.
        self.setContentsMargins(8, 0, 8, 0)
        self._handle_position = 0
        self._pulse_radius = 0

        # Set fixed size policy to prevent expanding
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self.sizeHint())

        # Setup animations
        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(200)  # time in ms

        self.pulse_anim = QPropertyAnimation(self, b"pulse_radius", self)
        self.pulse_anim.setDuration(350)  # time in ms
        self.pulse_anim.setStartValue(10)
        self.pulse_anim.setEndValue(20)

        self.animations_group = QSequentialAnimationGroup()
        self.animations_group.addAnimation(self.animation)
        self.animations_group.addAnimation(self.pulse_anim)

        # Connect to state changes
        self.stateChanged.connect(self.setup_animation)

    def sizeHint(self) -> QSize:
        """Return the preferred size for the toggle switch."""
        return QSize(58, 45)

    def hitButton(self, pos: QPoint) -> bool:
        """Define the clickable area of the widget."""
        return self.contentsRect().contains(pos)

    @Slot(int)
    def setup_animation(self, value: int):
        """Setup and start the animation based on the new state."""
        self.animations_group.stop()
        if value:
            self.animation.setEndValue(1)
        else:
            self.animation.setEndValue(0)
        self.animations_group.start()

    def paintEvent(self, a0: QPaintEvent | None):
        """Custom paint event to draw the animated toggle switch."""
        if a0 is None:
            return
        cont_rect = self.contentsRect()
        handle_radius = round(0.24 * cont_rect.height())

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.setPen(self._transparent_pen)
        bar_rect = QRectF(0, 0, cont_rect.width() - handle_radius, 0.40 * cont_rect.height())
        bar_rect.moveCenter(QPointF(cont_rect.center()))
        rounding = bar_rect.height() / 2

        # the handle will move along this line
        trail_length = cont_rect.width() - 2 * handle_radius
        x_pos = cont_rect.x() + handle_radius + trail_length * self._handle_position

        # Draw pulse effect if animation is running
        if self.pulse_anim.state() == QPropertyAnimation.State.Running:
            p.setBrush(self._pulse_checked_animation if self.isChecked() else self._pulse_unchecked_animation)
            p.drawEllipse(QPointF(x_pos, bar_rect.center().y()), self._pulse_radius, self._pulse_radius)

        # Draw the toggle bar and handle based on state
        if self.isChecked():
            p.setBrush(self._bar_checked_brush)
            p.drawRoundedRect(bar_rect, rounding, rounding)
            p.setBrush(self._handle_checked_brush)
        else:
            p.setBrush(self._bar_brush)
            p.drawRoundedRect(bar_rect, rounding, rounding)
            p.setPen(self._light_grey_pen)
            p.setBrush(self._handle_brush)

        # Draw the handle
        p.drawEllipse(QPointF(x_pos, bar_rect.center().y()), handle_radius, handle_radius)

        p.end()

    def _get_handle_position(self) -> float:
        """Get the current handle position (0.0 to 1.0)."""
        return self._handle_position

    def _set_handle_position(self, pos: float):
        """Set the handle position and trigger a repaint."""
        self._handle_position = pos
        self.update()

    def _get_pulse_radius(self) -> float:
        """Get the current pulse radius."""
        return self._pulse_radius

    def _set_pulse_radius(self, pos: float):
        """Set the pulse radius and trigger a repaint."""
        self._pulse_radius = pos
        self.update()

    # Create Qt properties for animation
    handle_position = Property(float, _get_handle_position, _set_handle_position)
    pulse_radius = Property(float, _get_pulse_radius, _set_pulse_radius)


class VToggle(QWidget):
    """A wrapper widget that combines AnimatedToggle with functional behavior,
    similar to VSwitch but using the animated toggle component.
    """

    def __init__(
        self,
        setter: Callable[[bool], None],
        getter: Callable[[], bool] | None = None,
        *,
        text: str = "",
        parent: QWidget | None = None,
        bar_color: Qt.GlobalColor | str = Qt.GlobalColor.gray,
        checked_color: str = "#0078D4",  # Microsoft blue
        handle_color: Qt.GlobalColor = Qt.GlobalColor.white,
        pulse_unchecked_color: str = "#44999999",
        pulse_checked_color: str = "#440078D4",
    ):
        """Initialize the VToggle.

        Args:
            text: Text label for the toggle (currently not displayed)
            getter: Function to get the initial state
            setter: Callback function when state changes
            parent: Parent widget
            bar_color: Color of the toggle bar when unchecked
            checked_color: Color of the toggle bar and handle when checked
            handle_color: Color of the toggle handle when unchecked
            pulse_unchecked_color: Color of the pulse effect when unchecked
            pulse_checked_color: Color of the pulse effect when checked

        """
        super().__init__(parent=parent)
        self.text = text
        self.getter = getter
        self.setter = setter
        self.log = logging.getLogger(f"VToggle[{id(self)}]")
        self._setup_ui(
            bar_color=bar_color,
            checked_color=checked_color,
            handle_color=handle_color,
            pulse_unchecked_color=pulse_unchecked_color,
            pulse_checked_color=pulse_checked_color,
        )

    @property
    def widget(self) -> QWidget:
        """Get the underlying widget for this input component."""
        return self

    def _setup_ui(
        self,
        bar_color: Qt.GlobalColor | str,
        checked_color: str,
        handle_color: Qt.GlobalColor,
        pulse_unchecked_color: str,
        pulse_checked_color: str,
    ):
        """Set up the user interface with the animated toggle."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create animated toggle
        self.toggle = _AnimatedToggle(
            bar_color=bar_color,
            checked_color=checked_color,
            handle_color=handle_color,
            pulse_unchecked_color=pulse_unchecked_color,
            pulse_checked_color=pulse_checked_color,
        )

        # Set the wrapper to also respect the toggle's fixed size
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self.toggle.sizeHint())

        # Set initial value from getter if provided
        if self.getter:
            try:
                initial_value = self.getter()
                self.toggle.setChecked(initial_value)
            except Exception:
                # If getter fails, just continue without setting value
                self.log.exception("Error getting initial value")

        # Connect callback if provided
        if self.setter:
            self.toggle.toggled.connect(self._on_toggled)

        layout.addWidget(self.toggle)

    def _on_toggled(self, checked: bool):
        """Handle toggle events."""
        if self.setter:
            self.setter(checked)

    def isChecked(self) -> bool:
        """Get the current checked state."""
        return self.toggle.isChecked()

    def setChecked(self, checked: bool):
        """Set the checked state."""
        self.toggle.setChecked(checked)

    def sizeHint(self) -> QSize:
        """Return the size hint from the underlying toggle."""
        return self.toggle.sizeHint()

    @property
    def toggled(self):
        """Forward the toggled signal from the underlying toggle."""
        return self.toggle.toggled


if __name__ == "__main__":
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QStyle, QVBoxLayout, QWidget

    def main():
        """Quick test of VToggle animation."""
        app = QApplication(sys.argv)
        app.setWindowIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        window = QWidget()
        window.setWindowTitle("VToggle Quick Test")
        window.setGeometry(300, 300, 300, 200)

        layout = QVBoxLayout(window)

        label = QLabel("VToggle Animation Test")
        layout.addWidget(label)

        # Update status when toggled
        def update_status(checked):
            status.setText(f"Toggle: {'ON' if checked else 'OFF'}")
            print(f"VToggle state changed: {'ON' if checked else 'OFF'}")

        # Create a VToggle
        toggle = VToggle(setter=update_status)
        layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignCenter)

        # Status label
        status = QLabel("Toggle: OFF")
        layout.addWidget(status)

        window.show()

        print("VToggle test window opened. Click the toggle to test animation!")
        print("The toggle should smoothly animate between states with a pulse effect.")

        return app.exec()

    sys.exit(main())

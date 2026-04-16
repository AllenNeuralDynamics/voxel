"""Preview widget for displaying multi-channel camera feed with pan/zoom."""

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from vxl.camera.preview import PreviewViewport
from vxl_qt.store import (
    PreviewStore,
    blur_image,
    composite_rgb,
    crop_image,
    resize_image,
)
from vxl_qt.ui.assets import VOXEL_LOGO
from vxl_qt.ui.kit import Colors


def clamp_top_left(value: float, view_size: float) -> float:
    """Clamp the top-left coordinate so the view stays within bounds."""
    return max(0.0, min(value, 1.0 - view_size))


class PreviewPanel(QWidget):
    """Displays preview image with pan/zoom interaction.

    Reads frame data from app.preview store and uses pure compositing functions.
    Handles mouse events for pan/zoom and updates store state.
    """

    viewport_changed = Signal(float, float, float, float)  # x, y, w, h

    MIN_VIEWPORT = 0.01
    ZOOM_SENSITIVITY = 0.001
    VIEWPORT_DEBOUNCE_MS = 100

    def __init__(self, store: PreviewStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        self.setStyleSheet(f"""
            PreviewPanel {{
                background-color: {Colors.BG_DARK};
                border: 1px solid {Colors.SUCCESS};
            }}
        """)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image_label.setScaledContents(False)
        layout.addWidget(self._image_label)

        self._original_pixmap: QPixmap | None = None

        # Pan state
        self._is_panning = False
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0
        self._pan_start_viewport = PreviewViewport()

        # Debounce timer
        self._viewport_debounce_timer = QTimer(self)
        self._viewport_debounce_timer.setSingleShot(True)
        self._viewport_debounce_timer.timeout.connect(self._emit_viewport_changed)

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Connect to store signals
        self._store.composite_updated.connect(self._update_display)

        self._load_default_image()

    @property
    def viewport(self) -> PreviewViewport:
        """Current viewport state."""
        return self._store.viewport

    def reset(self) -> None:
        """Reset preview state."""
        self._store.reset()
        self._load_default_image()

    def reset_viewport(self) -> None:
        """Reset pan/zoom to show full image."""
        self._store.set_viewport(PreviewViewport())
        self._schedule_viewport_changed()

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = True
            self._store.set_interacting(True)
            self._pan_start_x = event.position().x()
            self._pan_start_y = event.position().y()
            self._pan_start_viewport = self._store.viewport.model_copy()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if event is None or not self._is_panning:
            return

        width = self.width()
        height = self.height()
        if width <= 0 or height <= 0:
            return

        vp = self._store.viewport
        dx = ((event.position().x() - self._pan_start_x) / width) * vp.w
        dy = ((event.position().y() - self._pan_start_y) / height) * vp.h
        new_x = clamp_top_left(self._pan_start_viewport.x - dx, vp.w)
        new_y = clamp_top_left(self._pan_start_viewport.y - dy, vp.h)

        self._store.set_viewport(PreviewViewport(x=new_x, y=new_y, w=vp.w, h=vp.h))

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_panning = False
            self._store.set_interacting(False)
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._schedule_viewport_changed()

    def wheelEvent(self, event: QWheelEvent | None) -> None:
        if event is None:
            return

        pos = event.position()
        widget_width = self.width()
        widget_height = self.height()
        if widget_width <= 0 or widget_height <= 0:
            return

        mouse_x = pos.x() / widget_width
        mouse_y = pos.y() / widget_height

        delta = event.angleDelta().y() * self.ZOOM_SENSITIVITY
        vp = self._store.viewport

        new_w = max(self.MIN_VIEWPORT, min(1.0, vp.w - delta))
        new_h = max(self.MIN_VIEWPORT, min(1.0, vp.h - delta))

        if new_w == vp.w and new_h == vp.h:
            return

        # Point on sensor under cursor
        sensor_x = vp.x + mouse_x * vp.w
        sensor_y = vp.y + mouse_y * vp.h

        # Recompute top-left so sensor point stays under cursor
        new_x = clamp_top_left(sensor_x - mouse_x * new_w, new_w)
        new_y = clamp_top_left(sensor_y - mouse_y * new_h, new_h)

        self._store.set_interacting(True)
        self._store.set_viewport(PreviewViewport(x=new_x, y=new_y, w=new_w, h=new_h))
        self._store.set_interacting(False)

        self._schedule_viewport_changed()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_viewport()

    def _update_display(self) -> None:
        """Composite and display frames from store.

        Applies viewport crop to each channel's overview frame, then composites.
        """
        channels = self._store.channels
        if not channels:
            return

        vp = self._store.viewport
        is_zoomed = vp.w < 1.0 or vp.h < 1.0

        cropped_frames = [crop_image(ch.frame, vp) for ch in channels.values()]

        rgb = composite_rgb(cropped_frames)
        if rgb is None:
            return

        if self._store.is_interacting and is_zoomed:
            rgb = blur_image(rgb, radius=1.0)

        pixmap = self._numpy_to_pixmap(rgb)
        self._set_pixmap(pixmap)

    def _emit_viewport_changed(self) -> None:
        vp = self._store.viewport
        self.viewport_changed.emit(vp.x, vp.y, vp.w, vp.h)

    def _schedule_viewport_changed(self) -> None:
        self._viewport_debounce_timer.start(self.VIEWPORT_DEBOUNCE_MS)

    def _load_default_image(self) -> None:
        pixmap = QPixmap(str(VOXEL_LOGO))
        if pixmap.width() > 150:
            pixmap = pixmap.scaledToWidth(150, Qt.TransformationMode.SmoothTransformation)
        self._image_label.setPixmap(pixmap)
        self._original_pixmap = None

    def _set_pixmap(self, pixmap: QPixmap) -> None:
        self._original_pixmap = pixmap
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            return

        label_size = self._image_label.size()
        if label_size.width() < 1 or label_size.height() < 1:
            return

        scaled = self._original_pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _numpy_to_pixmap(self, rgb: np.ndarray) -> QPixmap:
        height, width = rgb.shape[:2]
        rgb = np.ascontiguousarray(rgb)
        bytes_per_line = rgb.strides[0]

        qimage = QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )

        return QPixmap.fromImage(qimage.copy())


class PreviewThumbnail(QWidget):
    """Small preview thumbnail showing full frames only.

    Always displays the full image (no crop/zoom), resized to target_width.
    Useful as a minimap or overview when zoomed in on the main preview.
    """

    def __init__(self, store: PreviewStore, target_width: int = 128, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._target_width = target_width

        self.setFixedWidth(target_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._image_label)

        self._store.composite_updated.connect(self._update_display)

    @property
    def target_width(self) -> int:
        return self._target_width

    @target_width.setter
    def target_width(self, value: int) -> None:
        self._target_width = value
        self.setFixedWidth(value)
        self._update_display()

    def _update_display(self) -> None:
        """Composite and display full frames from store."""
        channels = self._store.channels
        if not channels:
            return

        frames = [resize_image(ch.frame, self._target_width) for ch in channels.values()]

        rgb = composite_rgb(frames)
        if rgb is None:
            return

        pixmap = self._numpy_to_pixmap(rgb)
        self._image_label.setPixmap(pixmap)

    def _numpy_to_pixmap(self, rgb: np.ndarray) -> QPixmap:
        height, width = rgb.shape[:2]
        rgb = np.ascontiguousarray(rgb)
        bytes_per_line = rgb.strides[0]

        qimage = QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )

        return QPixmap.fromImage(qimage.copy())

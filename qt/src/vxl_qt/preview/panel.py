"""Preview widget: multi-channel camera feed with pan/zoom and viewport-image compositing.

Mirrors the web canvas model: per channel, a downsampled overview backdrop with one coherent high-res
viewport image overlaid for the zoomed region, each channel composited additively. Pan/zoom edits the
shared viewport (cropped locally via the pixel mapping, fed back to the cameras through ``viewport_changed``).
"""

import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from vxl.camera.preview import PreviewViewport
from vxl_qt.ui.assets import VOXEL_LOGO
from vxl_qt.ui.kit import Colors

from .models import ChannelData, PreviewStore


def clamp_top_left(value: float, view_size: float) -> float:
    """Clamp the top-left coordinate so the view stays within bounds."""
    return max(0.0, min(value, 1.0 - view_size))


def channel_bbox(channels: list[ChannelData]) -> tuple[int, int]:
    """Max sensor width/height across drawable channels (rotation-swapped) — the shared footprint."""
    max_w = max_h = 0
    for ch in channels:
        if (ch.frame is None and ch.view is None) or ch.sensor_w <= 0 or ch.sensor_h <= 0:
            continue
        swapped = ch.rotation_deg % 180 != 0
        max_w = max(max_w, ch.sensor_h if swapped else ch.sensor_w)
        max_h = max(max_h, ch.sensor_w if swapped else ch.sensor_h)
    return max_w, max_h


def sensor_to_stage(tx: float, ty: float, tw: float, th: float, rot: int) -> tuple[float, float, float, float]:
    """Rotate a sensor-normalized rect into the channel's stage-normalized footprint."""
    if rot == 90:
        return (1 - ty - th, tx, th, tw)
    if rot == 180:
        return (1 - tx - tw, 1 - ty - th, tw, th)
    if rot == 270:
        return (ty, 1 - tx - tw, th, tw)
    return (tx, ty, tw, th)


def draw_rotated(painter: QPainter, image: QImage, x: float, y: float, w: float, h: float, rot: int) -> None:
    """Draw ``image`` into the (x, y, w, h) rect, rotated ``rot`` degrees about the rect center."""
    if rot == 0:
        painter.drawImage(QRectF(x, y, w, h), image)
        return
    swapped = rot % 180 != 0
    painter.save()
    painter.translate(x + w / 2, y + h / 2)
    painter.rotate(rot)
    pw, ph = (h, w) if swapped else (w, h)
    painter.drawImage(QRectF(-pw / 2, -ph / 2, pw, ph), image)
    painter.restore()


class PreviewPanel(QWidget):
    """Displays the live preview (overview + viewport image) with pan/zoom interaction."""

    viewport_changed = Signal(float, float, float, float)  # x, y, w, h

    MIN_VIEWPORT = 0.01
    ZOOM_SENSITIVITY = 0.001
    PAN_ZOOM_STREAM_MS = 150  # tighter than web's 500 ms: Qt is local/in-process, settle is sub-frame

    def __init__(self, store: PreviewStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        self.setStyleSheet(
            f"PreviewPanel {{ background-color: {Colors.BG_DARK}; border: 1px solid {Colors.SUCCESS}; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self._image_label)

        # Pan state
        self._is_panning = False
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0
        self._pan_start_viewport = PreviewViewport()

        # Throttle feeding the viewport back to the cameras: leading + trailing, so pan/zoom
        # streams mid-gesture (at most one send per PAN_ZOOM_STREAM_MS) and always sends the last value.
        self._viewport_last_sent = 0.0
        self._viewport_throttle_timer = QTimer(self)
        self._viewport_throttle_timer.setSingleShot(True)
        self._viewport_throttle_timer.timeout.connect(self._emit_viewport_changed)

        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        # Coalesce repaints onto a timer so a burst of viewport changes (a pan drag fires mouse-move
        # ~100x/s) doesn't run a full composite synchronously per event and stall the UI thread.
        self._redraw_scheduled = False
        self._store.composite_updated.connect(self._request_redraw)
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
        """Reset pan/zoom to show the full image."""
        self._store.set_viewport(PreviewViewport())
        self._schedule_viewport_changed()

    # ── Interaction ────────────────────────────────────────────────

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
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return
        vp = self._store.viewport
        dx = ((event.position().x() - self._pan_start_x) / width) * vp.w
        dy = ((event.position().y() - self._pan_start_y) / height) * vp.h
        new_x = clamp_top_left(self._pan_start_viewport.x - dx, vp.w)
        new_y = clamp_top_left(self._pan_start_viewport.y - dy, vp.h)
        self._store.set_viewport(PreviewViewport(x=new_x, y=new_y, w=vp.w, h=vp.h))
        self._schedule_viewport_changed()

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
        cv_w, cv_h = self.width(), self.height()
        if cv_w <= 0 or cv_h <= 0:
            return

        # Aspect-fill zoom: adjust height by the wheel delta, derive width so the viewport's displayed
        # footprint keeps filling the canvas (matches the web), rather than zooming w/h independently.
        max_w, max_h = channel_bbox(list(self._store.channels.values()))
        bb_aspect = (max_w / max_h) if max_h else 1.0
        canvas_aspect = cv_w / cv_h

        mouse_x = event.position().x() / cv_w
        mouse_y = event.position().y() / cv_h

        delta = event.angleDelta().y() * self.ZOOM_SENSITIVITY
        vp = self._store.viewport
        new_h = max(self.MIN_VIEWPORT, min(1.0, vp.h - delta))
        new_w = max(self.MIN_VIEWPORT, min(1.0, (new_h * canvas_aspect) / bb_aspect))
        if new_w == vp.w and new_h == vp.h:
            return

        # Keep the sensor point under the cursor fixed across the zoom
        sensor_x = vp.x + mouse_x * vp.w
        sensor_y = vp.y + mouse_y * vp.h
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

    # ── Rendering ──────────────────────────────────────────────────

    def _request_redraw(self) -> None:
        """Schedule a single composite on the next timer tick, coalescing rapid updates."""
        if not self._redraw_scheduled:
            self._redraw_scheduled = True
            QTimer.singleShot(16, self._render)  # ~60 fps cap, off the event path

    def _render(self) -> None:
        self._redraw_scheduled = False
        self._update_display()

    def _update_display(self) -> None:
        """Composite the channels' overview + viewport image for the current viewport and show it."""
        channels = list(self._store.channels.values())
        cv_w, cv_h = self._image_label.width(), self._image_label.height()
        if cv_w < 1 or cv_h < 1:
            return
        max_w, max_h = channel_bbox(channels)
        if max_w <= 0 or max_h <= 0:
            self._image_label.clear()  # nothing to draw — blank so a cleared/switched profile doesn't linger
            return

        smooth = not self._store.is_interacting  # nearest-neighbor while panning/zooming; smooth when settled
        canvas = QPixmap(cv_w, cv_h)
        canvas.fill(QColor(0, 0, 0))  # black base so additive channel blending is correct
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
        self._composite(painter, cv_w, cv_h, channels, self._store.viewport, max_w, max_h, smooth)
        painter.end()
        self._image_label.setPixmap(canvas)

    def _composite(
        self,
        painter: QPainter,
        cv_w: int,
        cv_h: int,
        channels: list[ChannelData],
        vp: PreviewViewport,
        max_w: int,
        max_h: int,
        smooth: bool,
    ) -> None:
        # Contain-fit the viewport's footprint into the canvas (letterboxed)
        vp_aspect = (vp.w * max_w) / (vp.h * max_h)
        canvas_aspect = cv_w / cv_h
        if canvas_aspect > vp_aspect:
            draw_h = float(cv_h)
            draw_w = draw_h * vp_aspect
        else:
            draw_w = float(cv_w)
            draw_h = draw_w / vp_aspect
        draw_x = (cv_w - draw_w) / 2
        draw_y = (cv_h - draw_h) / 2

        def px_x(bb: float) -> float:
            return draw_x + ((bb - vp.x) / vp.w) * draw_w

        def px_y(bb: float) -> float:
            return draw_y + ((bb - vp.y) / vp.h) * draw_h

        def px_w(bb: float) -> float:
            return (bb / vp.w) * draw_w

        def px_h(bb: float) -> float:
            return (bb / vp.h) * draw_h

        for ch in channels:
            if (ch.frame is None and ch.view is None) or ch.sensor_w <= 0 or ch.sensor_h <= 0:
                continue
            rot = ch.rotation_deg % 360
            swapped = rot % 180 != 0
            scale_x = (ch.sensor_h if swapped else ch.sensor_w) / max_w
            scale_y = (ch.sensor_w if swapped else ch.sensor_h) / max_h
            offset_x = (1 - scale_x) / 2
            offset_y = (1 - scale_y) / 2

            # Per-channel offscreen: overview + view with source-over so the view cleanly replaces the
            # backdrop, then the whole layer is added onto the canvas (no double-brightness on overlap).
            layer = QImage(cv_w, cv_h, QImage.Format.Format_ARGB32_Premultiplied)
            layer.fill(Qt.GlobalColor.transparent)
            lp = QPainter(layer)
            lp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)

            if ch.frame is not None:
                draw_rotated(lp, ch.frame, px_x(offset_x), px_y(offset_y), px_w(scale_x), px_h(scale_y), rot)

            # Viewport image (high-res), positioned by its server-authoritative rect — only when zoomed
            if vp.needs_adjustment and ch.view is not None and ch.view_rect is not None:
                r = ch.view_rect
                sx, sy, sw, sh = sensor_to_stage(r.x, r.y, r.w, r.h, rot)
                tx, ty = px_x(offset_x + sx * scale_x), px_y(offset_y + sy * scale_y)
                tw, th = px_w(sw * scale_x), px_h(sh * scale_y)
                draw_rotated(lp, ch.view, tx, ty, tw, th, rot)
            lp.end()

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.drawImage(0, 0, layer)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    def _emit_viewport_changed(self) -> None:
        self._viewport_last_sent = time.monotonic() * 1000.0
        vp = self._store.viewport
        self.viewport_changed.emit(vp.x, vp.y, vp.w, vp.h)

    def _schedule_viewport_changed(self) -> None:
        elapsed = time.monotonic() * 1000.0 - self._viewport_last_sent
        if elapsed >= self.PAN_ZOOM_STREAM_MS:
            self._emit_viewport_changed()  # leading edge: fire now
        else:
            # trailing edge: coalesce to the window boundary
            self._viewport_throttle_timer.start(int(self.PAN_ZOOM_STREAM_MS - elapsed))

    def _load_default_image(self) -> None:
        pixmap = QPixmap(str(VOXEL_LOGO))
        if pixmap.width() > 150:
            pixmap = pixmap.scaledToWidth(150, Qt.TransformationMode.SmoothTransformation)
        self._image_label.setPixmap(pixmap)

    def resizeEvent(self, event: QResizeEvent | None) -> None:
        if event is not None:
            super().resizeEvent(event)
        self._request_redraw()


class PreviewThumbnail(QWidget):
    """Small overview-only thumbnail (no crop/zoom) — a minimap of the composited channels."""

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
        frames = [ch.frame for ch in self._store.channels.values() if ch.frame is not None]
        if not frames or frames[0].width() <= 0:
            self._image_label.clear()  # nothing to draw — blank so a cleared/switched profile doesn't linger
            return
        tw = self._target_width
        th = max(1, int(frames[0].height() * tw / frames[0].width()))
        canvas = QPixmap(tw, th)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for frame in frames:
            painter.drawImage(QRectF(0, 0, tw, th), frame)
        painter.end()
        self._image_label.setPixmap(canvas)

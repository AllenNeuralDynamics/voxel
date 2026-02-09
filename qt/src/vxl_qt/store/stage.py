"""Stage state store for Voxel application.

Caches stage axis properties (position, limits, is_moving) from device adapters
and emits Qt signals for reactive UI updates.
"""

import logging
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal

from vxl_qt.handle import DeviceHandleQt

log = logging.getLogger(__name__)


@dataclass
class AxisState:
    """Cached state for a single stage axis."""

    position: float = 0.0
    lower_limit: float = 0.0
    upper_limit: float = 100.0
    is_moving: bool = False

    @property
    def range(self) -> float:
        return self.upper_limit - self.lower_limit


class StageStore(QObject):
    """Manages stage axis state with Qt signals for reactive UI updates.

    Caches position, limits, and moving state for X, Y, Z axes from
    DeviceHandleQt adapters. Emits signals when state changes.

    Usage:
        store = StageStore()
        store.bind(x_adapter, y_adapter, z_adapter)

        store.position_changed.connect(on_position)
        store.moving_changed.connect(on_moving)
    """

    position_changed = Signal()
    moving_changed = Signal()
    limits_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.x = AxisState()
        self.y = AxisState()
        self.z = AxisState()

        self._x_adapter: DeviceHandleQt | None = None
        self._y_adapter: DeviceHandleQt | None = None
        self._z_adapter: DeviceHandleQt | None = None

    @property
    def is_xy_moving(self) -> bool:
        return self.x.is_moving or self.y.is_moving

    @property
    def is_z_moving(self) -> bool:
        return self.z.is_moving

    @property
    def stage_width(self) -> float:
        return self.x.range

    @property
    def stage_height(self) -> float:
        return self.y.range

    @property
    def stage_depth(self) -> float:
        return self.z.range

    @property
    def x_adapter(self) -> DeviceHandleQt | None:
        return self._x_adapter

    @property
    def y_adapter(self) -> DeviceHandleQt | None:
        return self._y_adapter

    @property
    def z_adapter(self) -> DeviceHandleQt | None:
        return self._z_adapter

    def bind(self, x_adapter: DeviceHandleQt, y_adapter: DeviceHandleQt, z_adapter: DeviceHandleQt) -> None:
        """Bind to stage axis adapters and subscribe to property updates."""
        self.unbind()

        self._x_adapter = x_adapter
        self._y_adapter = y_adapter
        self._z_adapter = z_adapter

        x_adapter.properties_changed.connect(self._on_x_props)
        y_adapter.properties_changed.connect(self._on_y_props)
        z_adapter.properties_changed.connect(self._on_z_props)

        x_adapter.request_initial_properties()
        y_adapter.request_initial_properties()
        z_adapter.request_initial_properties()

        log.info("StageStore bound to adapters: x=%s, y=%s, z=%s", x_adapter.uid, y_adapter.uid, z_adapter.uid)

    def unbind(self) -> None:
        """Disconnect from adapters and reset state."""
        if self._x_adapter is not None:
            self._x_adapter.properties_changed.disconnect(self._on_x_props)
        if self._y_adapter is not None:
            self._y_adapter.properties_changed.disconnect(self._on_y_props)
        if self._z_adapter is not None:
            self._z_adapter.properties_changed.disconnect(self._on_z_props)

        self._x_adapter = None
        self._y_adapter = None
        self._z_adapter = None

        self.x = AxisState()
        self.y = AxisState()
        self.z = AxisState()

    def _on_x_props(self, props: dict[str, Any]) -> None:
        self._update_axis(self.x, props)

    def _on_y_props(self, props: dict[str, Any]) -> None:
        self._update_axis(self.y, props)

    def _on_z_props(self, props: dict[str, Any]) -> None:
        self._update_axis(self.z, props)

    def _update_axis(self, axis: AxisState, props: dict[str, Any]) -> None:
        """Update an axis state from property dict and emit appropriate signals."""
        pos_changed = False
        moving_changed = False
        limits_changed = False

        if "position" in props:
            axis.position = float(props["position"])
            pos_changed = True

        if "lower_limit" in props:
            axis.lower_limit = float(props["lower_limit"])
            limits_changed = True

        if "upper_limit" in props:
            axis.upper_limit = float(props["upper_limit"])
            limits_changed = True

        if "is_moving" in props:
            axis.is_moving = bool(props["is_moving"])
            moving_changed = True

        if limits_changed:
            self.limits_changed.emit()
        if pos_changed:
            self.position_changed.emit()
        if moving_changed:
            self.moving_changed.emit()

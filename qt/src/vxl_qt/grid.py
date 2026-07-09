"""Grid panel — the planned acquisition tasks as an editable table.

Rows are the instrument's tasks (ordered by ``task_tiles``); columns expose each task's position,
z-range (editable), slice count, and profiles. Edits go through :meth:`Instrument.update_tasks` /
:meth:`Instrument.remove_tasks`; double-clicking a row moves the stage to that task's (x, y). Mirrors
main's ``GridTable`` on the task-centric domain (tasks/stencil/traversal) rather than the old row/col
tile grid.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from vxl.instrument import AcquisitionTask, Instrument, InstrumentState, TaskPatch
from vxl.traversal import Tile
from vxl_qt.devices.adapter import DevicesStore
from vxl_qt.devices.bind import bind_slider_spinbox
from vxl_qt.devices.stage import StageStore
from vxl_qt.ui.kit import (
    Colors,
    ColumnType,
    ControlSize,
    Flex,
    SliderSpinBox,
    Spacing,
    Stretch,
    Table,
    TableColumn,
    TableModel,
    Text,
    Toggle,
    hbox,
    vbox,
)
from vxlib import Teardown, fire_and_forget

log = logging.getLogger(__name__)

_MOSAIC_CAP = 10_000  # safety bound on computed mosaic cells, so a degenerate config can't freeze paint


@dataclass(frozen=True)
class _Row:
    """Per-row data the column getters read: the task plus the z_step that yields its slice count."""

    task: AcquisitionTask
    z_step: float | None


def _position_mm(task: AcquisitionTask) -> str:
    return f"{task.stack.x / 1000:.2f}, {task.stack.y / 1000:.2f}"


def _slices(row: _Row) -> str:
    if row.z_step is None or row.z_step <= 0:
        return "—"
    return str(row.task.stack.num_frames(row.z_step))


TASK_TABLE_COLUMNS: list[TableColumn] = [
    TableColumn(key="select", header="", column_type=ColumnType.CHECKBOX, width=32),
    TableColumn(key="task", header="Task", width=80, getter=lambda task_id, _r: str(task_id)[:8]),
    TableColumn(
        key="position",
        header="Position (mm)",
        width=None,
        min_width=110,
        getter=lambda _t, r: _position_mm(r.task) if r else "",
    ),
    TableColumn(
        key="z_start",
        header="Z Start",
        column_type=ColumnType.SPINBOX,
        width=90,
        getter=lambda _t, r: int(r.task.stack.start) if r else 0,
        setter=lambda _t, _r, v: {"start": v},
        editable=lambda _t, r: r is not None,
        suffix=" µm",
        min_val=-1000000,
        max_val=1000000,
        step=10,
    ),
    TableColumn(
        key="z_end",
        header="Z End",
        column_type=ColumnType.SPINBOX,
        width=90,
        getter=lambda _t, r: int(r.task.stack.end) if r else 0,
        setter=lambda _t, _r, v: {"end": v},
        editable=lambda _t, r: r is not None,
        suffix=" µm",
        min_val=-1000000,
        max_val=1000000,
        step=10,
    ),
    TableColumn(key="slices", header="Slices", width=60, align="right", getter=lambda _t, r: _slices(r) if r else "—"),
    TableColumn(
        key="profiles",
        header="Profiles",
        width=120,
        getter=lambda _t, r: ", ".join(r.task.profile_ids) if r else "",
    ),
]


class TasksTableModel(TableModel[str, "_Row | None"]):
    """Table model over the instrument's tasks. Rows are task ids (in ``task_tiles`` order); aux is the
    task + its z_step. Refreshes on every state commit; edits go through ``update_tasks``."""

    def __init__(self, instrument: Instrument, columns: list[TableColumn]) -> None:
        super().__init__(columns)
        self._instrument = instrument
        self._unsub = instrument.state.subscribe(lambda _state: self.refresh())

    def _snap(self) -> InstrumentState:
        return self._instrument.state.value

    def _get_rows(self) -> list[str]:
        return [tile.task_id for tile in self._instrument.task_tiles.value]

    def _get_aux_data(self, row_data: str) -> "_Row | None":
        snap = self._snap()
        task = snap.tasks.get(row_data)
        if task is None:
            return None
        z_step = None
        if task.profile_ids and (profile := snap.imaging.profiles.get(task.profile_ids[0])) is not None:
            z_step = profile.z_step
        return _Row(task, z_step)

    def _on_edit(self, row_data: str, aux_data: "_Row | None", column: TableColumn, value: Any) -> None:
        if aux_data is None or column.setter is None:
            return
        patch = TaskPatch(**column.setter(row_data, aux_data, value))
        fire_and_forget(self._instrument.update_tasks({row_data: patch}), log=log)

    def delete(self, task_ids: list[str]) -> None:
        """Remove the given tasks, then clear the checkbox selection."""
        fire_and_forget(self._instrument.remove_tasks(task_ids), log=log)
        self.clear_checked()

    def teardown(self) -> None:
        self._unsub()


class TasksTable(QWidget):
    """The grid tab: an editable table of the planned acquisition tasks. Check rows to multi-select;
    right-click for bulk actions (delete). Double-clicking a row moves the stage to that task."""

    def __init__(self, instrument: Instrument, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._model = TasksTableModel(instrument, TASK_TABLE_COLUMNS)
        self._table = Table(model=self._model, columns=TASK_TABLE_COLUMNS)
        self._table.row_double_clicked.connect(self._on_row_double_clicked)

        layout = vbox(self, margins=(0, 0, 0, 0))
        layout.addWidget(self._table)

    def _on_row_double_clicked(self, row_idx: int) -> None:
        """Move the stage to the double-clicked task's (x, y)."""
        task_id = self._model.get_row_at(row_idx)
        if task_id is None:
            return
        task = self._instrument.state.value.tasks.get(task_id)
        if task is None:
            return
        stage = self._instrument.hal.stage

        async def move() -> None:
            await asyncio.gather(stage.x.move_abs(task.x), stage.y.move_abs(task.y))

        fire_and_forget(move(), log=log)

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        """Right-click → bulk actions on the checkbox-selected tasks."""
        if event is None:
            return
        selected = self._model.get_checked_rows()
        if not selected:
            return
        menu = QMenu(self)
        menu.addAction(f"Delete selected ({len(selected)})", lambda: self._model.delete(selected))
        menu.exec(event.globalPos())

    def teardown(self) -> None:
        """Detach the model's bench subscription."""
        self._model.teardown()


class GridCanvas(QWidget):
    """Stage-space map of the plan: a mosaic-grid scaffold (FOV-sized cells from the stencil), the
    planned stacks stamped as FOV footprints, the traversal path, and the live stage FOV.

    Layers toggle independently. Single-click selects a stack; double-click a stack moves the stage
    there; double-click an empty grid cell stamps a new stack at it. The mosaic is computed UI-side
    (stencil + active FOV + stage bounds, mirroring the web); stacks come from ``instrument.task_tiles``.
    """

    def __init__(self, instrument: Instrument, stage: StageStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._stage = stage
        self._selected: str | None = None
        self._active_ids: set[str] = set()
        self._mosaic: list[Tile] = []  # computed grid scaffold (UI-side), and the stamp source
        self._layers = {"bounds": True, "grid": True, "stacks": True, "path": True, "fov": True}

        self.setStyleSheet(f"GridCanvas {{ background-color: {Colors.BG_DARK}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 100)
        self._build_layer_toggles()

        self._unsubs: list[Teardown] = [
            instrument.task_tiles.subscribe(self._refresh),
            instrument.active_profile_id.subscribe(self._refresh),
            instrument.fov.subscribe(self._recompute_mosaic),  # FOV drives both the live rect and the mosaic
            instrument.state.subscribe(self._recompute_mosaic),  # stencil edits change the mosaic
        ]
        stage.position_changed.connect(self.update)
        stage.moving_changed.connect(self.update)
        stage.limits_changed.connect(self._recompute_mosaic)  # stage bounds clip the mosaic
        self._refresh()
        self._recompute_mosaic()

    def teardown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self._stage.position_changed.disconnect(self.update)
        self._stage.moving_changed.disconnect(self.update)
        self._stage.limits_changed.disconnect(self._recompute_mosaic)

    def _build_layer_toggles(self) -> None:
        """Overlay (top-left) of per-layer visibility toggles: stage bounds, mosaic grid, planned
        stacks, traversal path, live FOV. Child widgets composite over the painted canvas; flipping
        one repaints with that layer hidden."""
        bar = QWidget()
        bar.setStyleSheet(f"background-color: {Colors.BG_LIGHT}; border-radius: 4px;")
        row = hbox(bar, spacing=Spacing.MD, margins=(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS))
        layers = (("bounds", "Bounds"), ("grid", "Grid"), ("stacks", "Stacks"), ("path", "Path"), ("fov", "FOV"))
        for key, label in layers:
            toggle = Toggle()
            toggle.setChecked(self._layers[key])
            toggle.toggled.connect(lambda checked, k=key: self._set_layer(k, checked))
            row.addWidget(Flex.hstack(Text.muted(label), toggle, spacing=Spacing.XS))

        outer = vbox(self, margins=(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM))
        outer.addWidget(Flex.hstack(bar, Stretch()))  # hug the top-left corner
        outer.addStretch(1)

    def _set_layer(self, key: str, visible: bool) -> None:
        self._layers[key] = visible
        self.update()

    def _refresh(self, _value: object = None) -> None:
        """Recompute which tasks belong to the active profile (for highlighting), then repaint."""
        active_id = self._instrument.active_profile_id.value
        tasks = self._instrument.state.value.tasks
        self._active_ids = {tid for tid, task in tasks.items() if active_id in task.profile_ids}
        self.update()

    def _recompute_mosaic(self, _arg: object = None) -> None:
        """Rebuild the mosaic-grid scaffold (stencil + active FOV + stage bounds), then repaint."""
        self._mosaic = self._compute_mosaic()
        self.update()

    def _compute_mosaic(self) -> list[Tile]:
        """Grid of FOV-sized cells whose *centers* tile the reachable stage range [lower, upper],
        stepped by FOV*(1-overlap) from the stencil offset. Centering on stage positions (not corners)
        is what makes a cell line up with the live FOV when the stage sits there; edge cells overshoot
        the bounds by half a FOV, which the padded viewbox keeps in view. Mirrors the web mosaic."""
        fov = self._instrument.fov.cache
        if fov is None:
            return []
        fw, fh = fov
        x, y = self._stage.x, self._stage.y
        x_lo, x_hi, y_lo, y_hi = x.lower_limit, x.upper_limit, y.lower_limit, y.upper_limit
        stencil = self._instrument.state.value.stencil
        step_x, step_y = fw * (1 - stencil.overlap_x), fh * (1 - stencil.overlap_y)
        if fw <= 0 or fh <= 0 or step_x <= 0 or step_y <= 0 or x_hi <= x_lo or y_hi <= y_lo:
            return []
        cells: list[Tile] = []
        cy = y_lo + stencil.y_offset
        while cy <= y_hi and len(cells) < _MOSAIC_CAP:
            cx = x_lo + stencil.x_offset
            while cx <= x_hi and len(cells) < _MOSAIC_CAP:
                if cx >= x_lo and cy >= y_lo:  # a negative offset can push the first center below the bound
                    cells.append(Tile(x=cx, y=cy, w=fw, h=fh))
                cx += step_x
            cy += step_y
        return cells

    def _transform(self) -> QTransform | None:
        """Stage-µm → screen-px. The viewbox is the stage bounds padded by half a FOV on every side,
        so a FOV or grid cell centered at a stage limit stays fully in view; same µm units and origin
        as tasks/position, Y points up."""
        x, y = self._stage.x, self._stage.y
        if x.range <= 0 or y.range <= 0:
            return None
        fov = self._instrument.fov.cache
        mx, my = (fov[0] / 2, fov[1] / 2) if fov is not None else (0.0, 0.0)  # half-FOV margin
        vb_x, vb_y, vb_w, vb_h = x.lower_limit - mx, y.lower_limit - my, x.range + 2 * mx, y.range + 2 * my
        scale = min(self.width() / vb_w, self.height() / vb_h)
        draw_w, draw_h = vb_w * scale, vb_h * scale
        ox, oy = (self.width() - draw_w) / 2, (self.height() - draw_h) / 2
        t = QTransform()
        t.translate(ox, oy + draw_h)
        t.scale(scale, -scale)  # flip Y so larger stage-Y is higher on screen
        t.translate(-vb_x, -vb_y)
        return t

    @staticmethod
    def _footprint(tile: Any) -> QRectF:
        return QRectF(tile.x - tile.w / 2, tile.y - tile.h / 2, tile.w, tile.h)

    def paintEvent(self, event: QPaintEvent | None) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(Colors.BG_DARK))
        transform = self._transform()
        if transform is None:
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setTransform(transform)
        stacks = {tile.task_id: tile for tile in self._instrument.task_tiles.value}

        # Stage bounds
        x, y = self._stage.x, self._stage.y
        if self._layers["bounds"]:
            self._stroke(painter, Colors.BORDER)
            painter.drawRect(QRectF(x.lower_limit, y.lower_limit, x.range, y.range))

        # Mosaic grid scaffold (the stamp source): FOV-sized cells over the stage, outline only
        if self._layers["grid"]:
            self._stroke(painter, Colors.BORDER)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for cell in self._mosaic:
                painter.drawRect(self._footprint(cell))

        # Planned stacks (footprints): active-profile stacks accented + faintly filled; others muted
        if self._layers["stacks"]:
            for tid, stack in stacks.items():
                if tid == self._selected:
                    self._stroke(painter, Colors.ACCENT_BRIGHT, width=2)
                elif tid in self._active_ids:
                    self._stroke(painter, Colors.ACCENT)
                else:
                    self._stroke(painter, Colors.TEXT_DISABLED)
                if tid in self._active_ids:
                    fill = QColor(Colors.ACCENT)
                    fill.setAlpha(40)
                    painter.setBrush(fill)
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(self._footprint(stack))

        # Traversal path through stack centers
        if self._layers["path"]:
            points = [QPointF(tile.x, tile.y) for tile in self._instrument.task_tiles.value]
            if len(points) > 1:
                self._stroke(painter, Colors.TEXT_MUTED)
                painter.drawPolyline(QPolygonF(points))

        # Live FOV at the current stage position
        if self._layers["fov"]:
            fov = self._instrument.fov.cache
            if fov is not None:
                cx, cy, (fw, fh) = x.position, y.position, fov
                self._stroke(painter, Colors.ERROR if self._stage.is_xy_moving else Colors.SUCCESS, width=2)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(cx - fw / 2, cy - fh / 2, fw, fh))

        painter.end()

    @staticmethod
    def _stroke(painter: QPainter, color: str, width: int = 1) -> None:
        pen = QPen(QColor(color))
        pen.setCosmetic(True)  # constant screen width regardless of the stage→screen scale
        pen.setWidth(width)
        painter.setPen(pen)

    def _task_at(self, pos: QPointF) -> str | None:
        transform = self._transform()
        if transform is None:
            return None
        inverse, ok = transform.inverted()
        if not ok:
            return None
        point = inverse.map(pos)
        for tile in self._instrument.task_tiles.value:
            if self._footprint(tile).contains(point):
                return tile.task_id
        return None

    def _cell_at(self, pos: QPointF) -> Tile | None:
        """The mosaic-grid cell under ``pos`` (screen → stage-µm), or None."""
        transform = self._transform()
        if transform is None:
            return None
        inverse, ok = transform.inverted()
        if not ok:
            return None
        point = inverse.map(pos)
        for cell in self._mosaic:
            if self._footprint(cell).contains(point):
                return cell
        return None

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is None:
            return
        self._selected = self._task_at(event.position())
        self.update()

    def contextMenuEvent(self, event: QContextMenuEvent | None) -> None:
        """Right-click a stack to move the stage there; right-click an empty grid cell to stamp a
        stack or move there."""
        if event is None:
            return
        pos = QPointF(event.pos())
        menu = QMenu(self)
        stacks = {tile.task_id: tile for tile in self._instrument.task_tiles.value}
        if (tid := self._task_at(pos)) is not None and (stack := stacks.get(tid)) is not None:
            menu.addAction("Move stage here", lambda: self._move_stage(stack.x, stack.y))
        elif (cell := self._cell_at(pos)) is not None:
            menu.addAction("Add stack here", lambda: self._add_stack(cell.x, cell.y))
            menu.addAction("Move stage here", lambda: self._move_stage(cell.x, cell.y))
        if not menu.isEmpty():
            menu.exec(event.globalPos())

    def _add_stack(self, x: float, y: float) -> None:
        fire_and_forget(self._instrument.add_tasks([(x, y)]), log=log)

    def _move_stage(self, x: float, y: float) -> None:
        stage = self._instrument.hal.stage

        async def move() -> None:
            await asyncio.gather(stage.x.move_abs(x), stage.y.move_abs(y))

        fire_and_forget(move(), log=log)


class StageControls(QWidget):
    """X/Y/Z slider+spinboxes bound to each stage axis's ``position`` property.

    The ``position`` model is deliminated, so a single property carries both the live value and the
    range (``minimum``/``maximum`` = the axis limits); :func:`bind_slider_spinbox` drives the range and
    value from it and, on edit (type or drag), sets ``position`` — the axis's settable-as-move setter —
    issuing an animated move. The spinbox follows the live position as the stage moves (from anywhere),
    pausing only while you're editing it. Binding waits for ``DevicesStore.ready`` so the controls pick
    up real limits the moment the adapters are live.
    """

    def __init__(self, instrument: Instrument, devices: DevicesStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._devices = devices
        cfg = instrument.hal.config.stage
        self._axis_uids = {"X": cfg.x, "Y": cfg.y, "Z": cfg.z}
        self._sliders: dict[str, SliderSpinBox] = {}
        self._bound = False

        layout = vbox(self, spacing=Spacing.XS, margins=(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM))
        for name in self._axis_uids:
            slider = SliderSpinBox(value=0.0, decimals=1, step=10.0, size=ControlSize.SM)  # range set on bind
            self._sliders[name] = slider
            layout.addWidget(Flex.hstack(Text.muted(name), (slider, 1), spacing=Spacing.SM))

        devices.ready.connect(self._bind)
        if devices.adapters:  # adapters already up (store started before this widget was built)
            self._bind()

    def _bind(self) -> None:
        """Bind each control to its axis ``position`` (range + live value + move-on-edit)."""
        if self._bound:
            return
        self._bound = True
        for name, uid in self._axis_uids.items():
            if (adapter := self._devices.get_adapter(uid)) is not None:
                bind_slider_spinbox(self._sliders[name], adapter, "position")

    def teardown(self) -> None:
        self._devices.ready.disconnect(self._bind)

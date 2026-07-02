"""Two-way bindings between kit widgets and a :class:`JsonCursor`.

Each ``bind_*`` connects a widget to a cursor: the cursor's value flows into the widget on every
commit that touches its path, and a user edit flows back out as a patch. The widget's change signal
is blocked while writing to it (no feedback loop), and the widget is re-seeded from the authoritative
value after each edit (so a validator clamp/rejection snaps it back). Each returns an unsubscribe
that detaches both directions — call it on teardown.
"""

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QSignalBlocker

from vxl_qt.state.cursor import JsonCursor
from vxl_qt.ui.kit.input import DoubleSpinBox, Select, SpinBox
from vxlib import Teardown, fire_and_forget

log = logging.getLogger(__name__)


def _commit(cur: JsonCursor, value: Any, reseed: Callable[[], None]) -> None:
    """Write ``value`` to the cursor, then re-seed the widget from the stored value (on success or
    rejection — the ``finally`` runs even if the patch is rejected, snapping the widget back)."""

    async def apply() -> None:
        try:
            await cur.set(value)
        finally:
            reseed()

    fire_and_forget(apply(), log=log)


def bind_spinbox(spin: SpinBox | DoubleSpinBox, cur: JsonCursor) -> Teardown:
    """Bind a spinbox to a numeric cursor."""

    def to_widget(value: Any) -> None:
        if value is not None:
            with QSignalBlocker(spin):
                spin.setValue(value)

    to_widget(cur.value)
    unsub = cur.subscribe(to_widget)
    conn = spin.valueChanged.connect(lambda v: _commit(cur, v, lambda: to_widget(cur.value)))

    def teardown() -> None:
        unsub()
        spin.valueChanged.disconnect(conn)

    return teardown


def bind_select(select: Select, cur: JsonCursor) -> Teardown:
    """Bind a dropdown to a cursor (e.g. an enum field)."""

    def to_widget(value: Any) -> None:
        with QSignalBlocker(select):
            select.set_value(value)

    to_widget(cur.value)
    unsub = cur.subscribe(to_widget)
    conn = select.value_changed.connect(lambda v: _commit(cur, v, lambda: to_widget(cur.value)))

    def teardown() -> None:
        unsub()
        select.value_changed.disconnect(conn)

    return teardown

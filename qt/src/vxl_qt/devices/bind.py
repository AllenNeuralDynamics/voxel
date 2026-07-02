"""Two-way bindings between kit widgets and device properties.

The device analog of :mod:`vxl_qt.state.bind` (which binds to bench ``JsonCursor`` state): these bind a
kit widget to a device property exposed by a :class:`DeviceHandleQt`. Enumerated **options** and numeric
**bounds** come from the property's cached model (:meth:`DeviceHandleQt.model` — populated from the
property stream, so they're device-native and handle dynamic options); the value reflects the stream,
and edits are pushed back via ``adapter.set``.

Unlike ``state.bind`` these return nothing: the binder is a child ``QObject`` of the widget, so Qt drops
its signal connections when the widget is destroyed — its lifetime follows the widget.
"""

import logging
from typing import Any

from PySide6.QtCore import QObject, QSignalBlocker, SignalInstance
from PySide6.QtWidgets import QApplication

from vxl_qt.devices.adapter import DeviceHandleQt
from vxl_qt.ui.kit import DoubleSpinBox, LockableSlider, Select, SliderSpinBox, SpinBox
from vxlib import fire_and_forget

log = logging.getLogger(__name__)


class _PropertyBinder(QObject):
    """Reflects a device property into a widget on stream updates and pushes edits back.

    Parented to the widget, so Qt removes the ``properties_changed`` connection when it is destroyed.
    Subclasses implement :meth:`_reflect` (model → widget) and connect the widget's change signal to
    :meth:`_push`.
    """

    def __init__(self, widget: QObject, adapter: DeviceHandleQt, prop: str) -> None:
        super().__init__(widget)
        self._adapter = adapter
        self._prop = prop
        adapter.properties_changed.connect(self._on_props)
        self._apply()  # apply the cached model if the property already streamed

    def _on_props(self, props: dict[str, Any]) -> None:
        if self._prop in props:
            self._apply()

    def _apply(self) -> None:
        if (model := self._adapter.model(self._prop)) is not None:
            self._reflect(model)

    def _reflect(self, model: Any) -> None:
        raise NotImplementedError

    def _push(self, value: Any) -> None:
        fire_and_forget(self._adapter.set(self._prop, value), log=log)


class _SelectBinder(_PropertyBinder):
    def __init__(self, select: Select, adapter: DeviceHandleQt, prop: str) -> None:
        self._select = select
        super().__init__(select, adapter, prop)
        select.value_changed.connect(self._push)

    def _reflect(self, model: Any) -> None:
        with QSignalBlocker(self._select):
            if model.options:
                self._select.set_options(list(model.options), model.value)
            else:
                self._select.set_value(model.value)


class _SpinBoxBinder(_PropertyBinder):
    def __init__(self, spin: SpinBox | DoubleSpinBox, adapter: DeviceHandleQt, prop: str) -> None:
        self._spin = spin
        super().__init__(spin, adapter, prop)
        spin.valueChanged.connect(self._push)

    def _reflect(self, model: Any) -> None:
        with QSignalBlocker(self._spin):
            if model.minimum is not None:
                self._spin.setMinimum(model.minimum)
            if model.maximum is not None:
                self._spin.setMaximum(model.maximum)
            if model.step is not None:
                self._spin.setSingleStep(model.step)
            self._spin.setValue(model.value)


class _SliderBinder(_PropertyBinder):
    """Bind a 3-layer slider (``LockableSlider`` or ``SliderSpinBox``) to a deliminated numeric property.

    The model supplies both the range (``minimum``/``maximum``) and the live value: ``_reflect`` drives
    the slider's *actual* layer and range from it on every update; committing — via the widget's own
    signal (release for a bare slider, value-change for a slider+spinbox) — pushes the new value through
    ``adapter.set`` (which, for a settable-as-move property like an axis ``position``, issues the move).

    ``sync_target`` governs the *target* layer on reflect: on (typical for a spinbox) → it follows the
    live value too, **except while the user has focus in the widget** (a focus guard, so a streamed
    update can't clobber what they're typing); off (a bare slider) → the target marks only the commanded
    destination, set on push, while *actual* tracks the live value toward it.
    """

    def __init__(
        self,
        slider: LockableSlider | SliderSpinBox,
        adapter: DeviceHandleQt,
        prop: str,
        committed: SignalInstance,
        *,
        sync_target: bool,
    ) -> None:
        self._slider = slider
        self._sync_target = sync_target
        super().__init__(slider, adapter, prop)
        committed.connect(self._push)

    def _reflect(self, model: Any) -> None:
        # range first, then value: setActual recomputes its ratio against the current min/max
        if model.minimum is not None and model.maximum is not None:
            self._slider.setRange(model.minimum, model.maximum)
        self._slider.setActual(model.value)
        # Track the live value on the spinbox/target too — but not while the user is editing it,
        # or a streamed update (e.g. a stage move from elsewhere) would clobber their input.
        if self._sync_target and not self._user_editing():
            self._slider.setTarget(model.value)

    def _user_editing(self) -> bool:
        """True while focus is within this widget (the user is typing/dragging it)."""
        focused = QApplication.focusWidget()
        return focused is not None and self._slider.isAncestorOf(focused)

    def _push(self, value: float) -> None:
        self._slider.setTarget(value)  # show the commanded value immediately
        super()._push(value)


def bind_select(select: Select, adapter: DeviceHandleQt, prop: str) -> None:
    """Two-way-bind ``select`` to the enumerated device property ``prop`` (options + value + edits)."""
    _SelectBinder(select, adapter, prop)


def bind_spinbox(spin: SpinBox | DoubleSpinBox, adapter: DeviceHandleQt, prop: str) -> None:
    """Two-way-bind ``spin`` to the numeric device property ``prop`` (bounds + value + edits)."""
    _SpinBoxBinder(spin, adapter, prop)


def bind_slider(slider: LockableSlider, adapter: DeviceHandleQt, prop: str) -> None:
    """Two-way-bind ``slider`` to a deliminated numeric ``prop`` (range + live value + move-on-release).

    For a moving device: *actual* tracks the live value; *target* marks the value released on.
    """
    _SliderBinder(slider, adapter, prop, slider.inputReleased, sync_target=False)


def bind_slider_spinbox(slider: SliderSpinBox, adapter: DeviceHandleQt, prop: str, *, sync_target: bool = True) -> None:
    """Two-way-bind ``slider`` to a deliminated numeric ``prop`` (range + value + edits).

    ``sync_target`` (default): the spinbox/target follow the device value when not being edited — right
    for an instant-settling control. Pass ``sync_target=False`` for a *moving* device (e.g. a stage axis)
    so the continuous position stream tracks only the *actual* bar and never clobbers the spinbox value.
    """
    _SliderBinder(slider, adapter, prop, slider.valueChanged, sync_target=sync_target)

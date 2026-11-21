"""Adapt a continuous axis into a set of named discrete positions."""

import math
import time
from collections.abc import Mapping
from contextlib import suppress

from pydantic import BaseModel, ConfigDict

from rigup import BuildConfig, build_objects
from vxl.devices.axes.continuous.base import ContinuousAxis
from vxl.devices.axes.discrete.base import DiscreteAxis, DiscreteAxisState, SlotName


class MappedSlot(BaseModel):
    """One discrete slot represented by an absolute continuous-axis position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: float
    label: SlotName | None = None


_POLL_S = 0.01
"""How often a wait asks the continuous axis whether it still moves."""


class MappedDiscreteAxis(DiscreteAxis):
    """Present fixed positions on any injected continuous axis as discrete slots.

    The adapter borrows the underlying axis; rigup remains responsible for closing
    that device. Positions outside every slot's tolerance resolve to ``None``. ``home`` names the slot, by index or
    label, that :meth:`home` moves to; without it the axis cannot home.
    """

    def __init__(
        self,
        device_id: str,
        *,
        axis: ContinuousAxis,
        slots: Mapping[int | str, MappedSlot | Mapping[str, object]],
        tolerance: float,
        home: int | str | None = None,
    ) -> None:
        specs = {int(index): MappedSlot.model_validate(spec) for index, spec in slots.items()}
        self._validate_specs(specs, tolerance)

        super().__init__(
            device_id=device_id,
            slots={index: spec.label for index, spec in specs.items()},
            slot_count=len(specs),
        )
        self._axis = axis
        self._specs = specs
        self._tolerance = float(tolerance)
        self._target: int | None = None
        self._home = None if home is None else self._slot_named(home)

    @property
    def state(self) -> DiscreteAxisState:
        is_moving = self._axis.is_moving
        physical_position = self._axis.position
        return DiscreteAxisState(
            position=self._slot_at(physical_position),
            target=self._target,
            is_moving=is_moving,
        )

    def _slot_at(self, physical_position: float) -> int | None:
        candidates = [
            (abs(physical_position - spec.position), index)
            for index, spec in self._specs.items()
            if abs(physical_position - spec.position) <= self._tolerance
        ]
        return min(candidates)[1] if candidates else None

    def move_to_slot(self, slot: int, *, wait: bool = False, timeout_s: float | None = None) -> None:
        try:
            target = self._specs[slot].position
        except KeyError as exc:
            raise ValueError(f"Invalid slot {slot}; valid slots are {sorted(self._specs)}") from exc
        self._axis.move_to(target)
        self._target = slot
        if wait:
            self.await_movement(timeout_s)

    def home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to the ``home`` slot. Raise when none was given."""
        if self._home is None:
            raise RuntimeError(f"{self.id} has no home slot")
        self.move_to_slot(self._home, wait=wait, timeout_s=timeout_s)

    def halt(self) -> None:
        self._axis.halt()

    def await_movement(self, timeout_s: float | None = None) -> None:
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        while self._axis.is_moving:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"{self.id} still moves after {timeout_s} s")
            time.sleep(_POLL_S)

    def _slot_named(self, slot: int | str) -> int:
        """The index of ``slot``, given by index or by label."""
        if isinstance(slot, int):
            if slot not in self._specs:
                raise ValueError(f"No slot {slot}; valid slots are {sorted(self._specs)}")
            return slot
        return self.index_of(slot)

    @staticmethod
    def _validate_specs(specs: dict[int, MappedSlot], tolerance: float) -> None:
        if not specs:
            raise ValueError("slots must define at least one mapped position")
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be finite and greater than zero")

        expected = set(range(len(specs)))
        if set(specs) != expected:
            raise ValueError(f"slot indices must be contiguous from 0; expected {sorted(expected)}")

        labels = [spec.label for spec in specs.values() if spec.label is not None]
        if len(labels) != len(set(labels)):
            raise ValueError("mapped slot labels must be unique")

        for index, spec in specs.items():
            if not math.isfinite(spec.position):
                raise ValueError(f"slot {index} position must be finite")

        for left_index, left in specs.items():
            for right_index, right in specs.items():
                if right_index <= left_index:
                    continue
                if abs(left.position - right.position) <= 2 * tolerance:
                    raise ValueError(f"slots {left_index} and {right_index} overlap within tolerance {tolerance}")


class OwnedMappedDiscreteAxis(MappedDiscreteAxis):
    """Map discrete positions onto a private continuous axis built from configuration.

    Unlike :class:`MappedDiscreteAxis`, this adapter owns the constructed axis and
    closes it with the adapter. The child is an implementation detail: it does not
    receive a separate rig handle or expose its own interface.
    """

    def __init__(
        self,
        device_id: str,
        *,
        axis: BuildConfig | Mapping[str, object],
        slots: Mapping[int | str, MappedSlot | Mapping[str, object]],
        tolerance: float,
        home: int | str | None = None,
    ) -> None:
        axis_config = axis if isinstance(axis, BuildConfig) else BuildConfig.model_validate(axis)
        axis_id = f"{device_id}_axis"
        built, errors = build_objects({axis_id: axis_config}, base_cls=ContinuousAxis)
        if error := errors.get(axis_id):
            raise RuntimeError(f"Unable to build owned axis for '{device_id}' ({error.code}): {error.msg}")

        child = built.get(axis_id)
        if not isinstance(child, ContinuousAxis):
            if child is not None:
                with suppress(Exception):
                    child.dispose()
            actual = type(child).__name__ if child is not None else "None"
            raise TypeError(f"Owned axis for '{device_id}' must be a continuous axis, got {actual}")

        try:
            super().__init__(
                device_id=device_id,
                axis=child,
                slots=slots,
                tolerance=tolerance,
                home=home,
            )
        except Exception:
            with suppress(Exception):
                child.dispose()
            raise

        self._owned_axis = child
        self._owned_axis_closed = False

    def dispose(self) -> None:
        if self._owned_axis_closed:
            return
        self._owned_axis_closed = True
        self._owned_axis.dispose()

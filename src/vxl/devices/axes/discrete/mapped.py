"""Adapt a continuous axis into a set of named discrete positions."""

import math
from collections.abc import Mapping
from contextlib import suppress

from pydantic import BaseModel, ConfigDict

from rigup import BuildConfig, build_objects
from vxl.devices.axes.continuous import ContinuousAxis
from vxl.devices.axes.discrete.base import DiscreteAxis, DiscreteAxisState


class MappedSlot(BaseModel):
    """One discrete slot represented by an absolute continuous-axis position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: float
    label: str | None = None


class MappedDiscreteAxis(DiscreteAxis):
    """Present fixed positions on any injected continuous axis as discrete slots.

    The adapter borrows the underlying axis; rigup remains responsible for closing
    that device. Positions outside every slot's tolerance resolve to ``None``.
    """

    def __init__(
        self,
        uid: str,
        *,
        axis: ContinuousAxis,
        slots: Mapping[int | str, MappedSlot | Mapping[str, object]],
        tolerance: float,
    ) -> None:
        specs = {int(index): MappedSlot.model_validate(spec) for index, spec in slots.items()}
        self._validate_specs(specs, tolerance)

        super().__init__(
            uid=uid,
            slots={index: spec.label for index, spec in specs.items()},
            slot_count=len(specs),
        )
        self._axis = axis
        self._specs = specs
        self._tolerance = float(tolerance)
        self._target: int | None = None

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

    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        try:
            target = self._specs[slot].position
        except KeyError as exc:
            raise ValueError(f"Invalid slot {slot}; valid slots are {sorted(self._specs)}") from exc
        self._axis.move_abs(target, wait=False)
        self._target = slot
        if wait:
            self.await_movement(timeout)

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        home_position = self._axis.home
        target = self._slot_at(home_position) if home_position is not None else None
        self._axis.go_home(wait=False)
        self._target = target
        if wait:
            self.await_movement(timeout)

    def halt(self) -> None:
        self._axis.halt()

    def await_movement(self, timeout: float | None = None) -> None:
        self._axis.await_movement(timeout_s=timeout)

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
        uid: str,
        *,
        axis: BuildConfig | Mapping[str, object],
        slots: Mapping[int | str, MappedSlot | Mapping[str, object]],
        tolerance: float,
    ) -> None:
        axis_config = axis if isinstance(axis, BuildConfig) else BuildConfig.model_validate(axis)
        axis_uid = f"{uid}_axis"
        built, errors = build_objects({axis_uid: axis_config}, base_cls=ContinuousAxis)
        if error := errors.get(axis_uid):
            raise RuntimeError(f"Unable to build owned axis for '{uid}' ({error.error_type}): {error.message}")

        child = built.get(axis_uid)
        if not isinstance(child, ContinuousAxis):
            if child is not None:
                with suppress(Exception):
                    child.close()
            actual = type(child).__name__ if child is not None else "None"
            raise TypeError(f"Owned axis for '{uid}' must be a ContinuousAxis, got {actual}")

        try:
            super().__init__(
                uid=uid,
                axis=child,
                slots=slots,
                tolerance=tolerance,
            )
        except Exception:
            with suppress(Exception):
                child.close()
            raise

        self._owned_axis = child
        self._owned_axis_closed = False

    def close(self) -> None:
        if self._owned_axis_closed:
            return
        self._owned_axis_closed = True
        self._owned_axis.close()

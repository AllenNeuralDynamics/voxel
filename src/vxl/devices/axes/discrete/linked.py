"""Several discrete axes that move together as 1, such as 2 flip mirrors that redirect the light."""

import time
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from vxl.devices.axes.discrete.base import DiscreteAxis, DiscreteAxisState


class LinkedSlot(BaseModel):
    """1 slot of the linked axis: a label, and the label of each member's slot, by member UID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = None
    positions: dict[str, str] = Field(min_length=1)


class LinkedDiscreteAxis(DiscreteAxis):
    """Move several discrete axes as 1, with named slots.

    Moving to a slot moves each member to its position, in the order of ``axes``, then waits when asked. The position
    is the slot whose member positions all match, or ``None``. The axis borrows its members; rigup closes them, and the
    members run on the same node.
    """

    def __init__(
        self,
        uid: str,
        *,
        axes: Sequence[DiscreteAxis],
        slots: Mapping[int | str, LinkedSlot | Mapping[str, object]],
    ) -> None:
        specs = {int(index): LinkedSlot.model_validate(spec) for index, spec in slots.items()}
        members = list(axes)
        targets = self._targets(specs, members)
        super().__init__(uid=uid, slots={index: spec.label for index, spec in specs.items()}, slot_count=len(specs))
        self._members = members
        self._slot_targets = targets
        self._target: int | None = None

    @property
    def state(self) -> DiscreteAxisState:
        states = {member.uid: member.state for member in self._members}
        position = next(
            (
                index
                for index, targets in self._slot_targets.items()
                if all(states[uid].position == slot for uid, slot in targets.items())
            ),
            None,
        )
        is_moving = any(state.is_moving for state in states.values())
        return DiscreteAxisState(position=position, target=self._target, is_moving=is_moving)

    def move(self, slot: int, *, wait: bool = False, timeout: float | None = None) -> None:
        targets = self._slot_targets.get(slot)
        if targets is None:
            raise ValueError(f"Invalid slot {slot}; valid slots are {sorted(self._slot_targets)}")
        for member in self._members:
            member.move(targets[member.uid], wait=False)
        self._target = slot
        if wait:
            self.await_movement(timeout)

    def home(self, *, wait: bool = False, timeout: float | None = None) -> None:
        for member in self._members:
            member.home(wait=False)
        self._target = None
        if wait:
            self.await_movement(timeout)

    def halt(self) -> None:
        for member in self._members:
            member.halt()

    def await_movement(self, timeout: float | None = None) -> None:
        deadline = time.monotonic() + timeout if timeout is not None else None
        for member in self._members:
            left = None if deadline is None else max(0.0, deadline - time.monotonic())
            member.await_movement(left)

    @staticmethod
    def _targets(specs: Mapping[int, LinkedSlot], members: Sequence[DiscreteAxis]) -> dict[int, dict[str, int]]:
        """Each slot's member slot indices, by member UID. Raise ``ValueError`` for a slot that cannot be reached."""
        if not specs:
            raise ValueError("slots must define at least 1 linked position")
        if set(specs) != set(range(len(specs))):
            raise ValueError(f"slot indices must be contiguous from 0; expected {list(range(len(specs)))}")
        labels = [spec.label for spec in specs.values() if spec.label is not None]
        if len(labels) != len(set(labels)):
            raise ValueError("linked slot labels must be unique")
        uids = [member.uid for member in members]
        if not uids or len(uids) != len(set(uids)):
            raise ValueError("axes must list at least 1 member, each once")
        targets: dict[int, dict[str, int]] = {}
        for index, spec in specs.items():
            if set(spec.positions) != set(uids):
                raise ValueError(f"slot {index} must give a position for exactly the members {uids}")
            found: dict[str, int] = {}
            for member in members:
                label = spec.positions[member.uid]
                try:
                    found[member.uid] = member.index_of(label)
                except KeyError:
                    raise ValueError(f"slot {index}: '{label}' is not a slot of member '{member.uid}'") from None
            targets[index] = found
        repeats = [index for index, found in targets.items() if list(targets.values()).index(found) != index]
        if repeats:
            raise ValueError(f"slots {repeats} repeat the member positions of an earlier slot")
        return targets


__all__ = ["LinkedDiscreteAxis", "LinkedSlot"]

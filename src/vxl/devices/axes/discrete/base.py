from abc import abstractmethod
from collections.abc import Mapping
from typing import Annotated

from pydantic import BaseModel, BeforeValidator
from vxlib.schema import check_identifier

from rigup import RigComponent, describe
from vxl.devices.axes.base import Axis
from vxl.devices.base import DeviceType

type SlotContent = str | RigComponent | None
"""What a slot holds: a plain name, a component such as a filter, or nothing that the rig names."""


def slot_label(content: object) -> object:
    """The label of a slot: the name of the component that it holds, or ``content`` itself when it is a name."""
    if content is None or isinstance(content, str):
        return content
    return getattr(content, "uid", content)


SlotName = Annotated[str, BeforeValidator(slot_label)]
"""A slot label in the slot settings of a driver. A component given in its place counts as its name."""


class DiscreteAxisState(BaseModel, frozen=True):
    """Discrete-axis feedback and command state.

    ``position`` is a feedback-resolved slot or ``None``. ``target`` retains the
    last successfully issued slot across arrival, halt, timeout, and external moves.
    Both indices are zero-based; an unset target is ``None``.
    """

    position: int | None
    target: int | None
    is_moving: bool


class DiscreteAxis(Axis[str], kind=DeviceType.DISCRETE_AXIS):
    """Named discrete slots with synchronous motion commands and streamed state."""

    def __init__(
        self,
        uid: str,
        slots: Mapping[int | str, SlotContent],
        slot_count: int | None = None,
    ) -> None:
        """Define zero-based slots, inferring slot count from the largest index when omitted.

        String keys are normalized to integers; missing labels remain ``None``. A label has the form of a name:
        letters, digits, ``_`` and ``-``. A slot that holds a component takes the name of that component.
        """
        super().__init__(uid=uid)

        # Normalize slots: convert string keys to int (YAML might parse numeric keys as strings)
        normalized_slots: dict[int, str | None] = {}
        for key, content in slots.items():
            label = slot_label(content)
            if label is not None and not isinstance(label, str):
                raise TypeError(f"slot {key} holds {content!r}, which is neither a name nor a component")
            if label is not None:
                check_identifier(label, "Slot label")
            normalized_slots[int(key)] = label

        # Determine slot count
        max_idx = max(normalized_slots.keys()) if normalized_slots else -1
        self._slot_count = slot_count if slot_count is not None else (max_idx + 1)
        if self._slot_count <= 0:
            raise ValueError("slot_count must be > 0")

        # Fill missing indices with None; enforce 0-based contiguous indices
        self._labels: dict[int, str | None] = {i: normalized_slots.get(i) for i in range(self._slot_count)}

    # State properties _______________________________________________________________________________________________

    @property
    @describe(label="Slot Count", desc="Total number of physical slots.")
    def slot_count(self) -> int:
        """Physical slot count."""
        return self._slot_count

    @property
    @describe(label="Labels", desc="Map of slot index to human-readable label.")
    def labels(self) -> Mapping[int, str | None]:
        """Slot labels; ``None`` denotes an unlabeled slot."""
        return self._labels

    @property
    @abstractmethod
    @describe(label="State", desc="Current slot, last commanded slot, and movement status.", stream=True)
    def state(self) -> DiscreteAxisState:
        """Read a coherent snapshot; propagate communication errors."""

    # Motion commands ________________________________________________________________________________________________

    @abstractmethod
    @describe(label="Move To Slot", desc="Move to a slot by index.", stream=True)
    def move_to_slot(self, slot: int, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Command a slot, optionally waiting for completion.

        ``timeout_s`` bounds the wait in seconds. Invalid slots raise ``ValueError``;
        an expired wait raises ``TimeoutError``.
        """

    @describe(label="Move To", desc="Move to a slot by its label.", stream=True)
    def move_to(self, position: str, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Command the first slot whose label is ``position``.

        A missing label raises ``KeyError``. Wait and timeout semantics match ``move_to_slot``. A slot with no
        label is reached with ``move_to_slot``.
        """
        try:
            slot = self.index_of(position)
        except KeyError:
            raise KeyError(f"Label not found: {position!r}") from None
        self.move_to_slot(slot, wait=wait, timeout_s=timeout_s)

    @abstractmethod
    @describe(label="Home", desc="Home/calibrate the device.", stream=True)
    def home(self, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Home the axis using the wait and timeout semantics of ``move_to_slot``."""

    @abstractmethod
    @describe(label="Halt", desc="Emergency stop - halt all motion immediately.", stream=True)
    def halt(self) -> None:
        """Halt motion immediately."""

    @abstractmethod
    @describe(label="Await Movement", desc="Wait until the device stops moving.", stream=True)
    def await_movement(self, timeout_s: float | None = None) -> None:
        """Wait for idle; ``timeout_s`` is in seconds, with ``None`` unbounded.

        An expired wait raises ``TimeoutError``.
        """

    # Helper methods _________________________________________________________________________________________________

    def index_of(self, label: str) -> int:
        """Return the first slot matching ``label``; raise ``KeyError`` if absent."""
        for i in range(self._slot_count):
            if self._labels.get(i) == label:
                return i
        raise KeyError(label)

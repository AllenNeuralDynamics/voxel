"""In-memory undo/redo history, serialized by its owner rather than an internal lock."""

from collections.abc import Awaitable, Callable, Hashable
from copy import deepcopy
from dataclasses import dataclass

from vxlib.reactivity import Cell, Readable, ReadableView
from vxlib.schema import FrozenModel


class Change[T](FrozenModel):
    """Values before and after a committed edit; nested values may still be mutable."""

    before: T
    after: T


class HistoryState(FrozenModel):
    """Descriptions of the next undo and redo actions; ``None`` means the stack is empty."""

    undo_label: str | None = None
    redo_label: str | None = None


@dataclass
class _Entry:
    label: str
    undo: Callable[[], Awaitable[None]]
    redo: Callable[[], Awaitable[None]]
    merge_key: Hashable | None


class UndoHistory:
    """Bounded history of successful edits with optional gesture-based merging.

    The owner must serialize the original mutation and ``record`` together with
    ``undo``, ``redo``, and ``clear`` (for example, under an Instrument lock).
    Restore callbacks validate and apply values without recording another entry;
    callbacks and state subscribers must not re-enter this history.

    Only affected values are retained, copied on recording and before each replay.
    Values must support equality and deepcopy. History does not persist entries,
    drive hardware, detect external conflicts, or roll back a partially failed
    restore. A failed or cancelled restore leaves its entry available for recovery.
    """

    def __init__(self, capacity: int = 50) -> None:
        if capacity < 1:
            raise ValueError("History capacity must be positive")
        self._capacity = capacity
        self._past: list[_Entry] = []
        self._future: list[_Entry] = []
        self._state = Cell(HistoryState())

    @property
    def state(self) -> Readable[HistoryState]:
        """Read-only reactive labels, updated after successful history transitions."""
        return ReadableView(self._state)

    async def record[T](
        self,
        label: str,
        change: Change[T],
        restore: Callable[[T], Awaitable[object]],
        *,
        merge_key: Hashable | None = None,
    ) -> None:
        """Record an already committed edit; equal before/after values are ignored.

        Reuse a merge key only for consecutive edits to the same target and scope
        within one gesture. Merging keeps the first undo and the latest redo.
        Replay breaks merging; every non-no-op edit discards the redo branch.
        """
        if change.before == change.after:
            return
        before = deepcopy(change.before)
        after = deepcopy(change.after)

        async def undo() -> None:
            await restore(deepcopy(before))

        async def redo() -> None:
            await restore(deepcopy(after))

        last = self._past[-1] if self._past else None
        if merge_key is not None and last is not None and last.merge_key == merge_key:
            last.redo = redo
        else:
            self._past.append(_Entry(label, undo, redo, merge_key))
            if len(self._past) > self._capacity:
                del self._past[: len(self._past) - self._capacity]
        self._future.clear()
        await self._publish()

    async def undo(self) -> None:
        """Restore the previous values; move the entry only after the callback succeeds."""
        self._break_merge()
        if not self._past:
            return
        entry = self._past[-1]
        await entry.undo()
        self._past.pop()
        self._future.append(entry)
        self._break_merge()
        await self._publish()

    async def redo(self) -> None:
        """Restore the committed values; move the entry only after the callback succeeds."""
        self._break_merge()
        if not self._future:
            return
        entry = self._future[-1]
        await entry.redo()
        self._future.pop()
        self._past.append(entry)
        await self._publish()

    async def clear(self) -> None:
        """Discard entries and their captured values without executing any callbacks."""
        self._past.clear()
        self._future.clear()
        await self._publish()

    def _break_merge(self) -> None:
        if self._past:
            self._past[-1].merge_key = None

    async def _publish(self) -> None:
        await self._state.set(
            HistoryState(
                undo_label=self._past[-1].label if self._past else None,
                redo_label=self._future[-1].label if self._future else None,
            )
        )

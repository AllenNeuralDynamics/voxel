# /// script
# requires-python = ">=3.13"
# dependencies = ["pydantic>=2"]
# ///
"""Spike: frozen InstrumentState + a state-native, sharing Document.

Run with: ``uv run vxlib/scripts/immutable_state.py``

Demonstrates the design we converged on:

* The state tree is FROZEN, so the Document hands the *same* live reference to
  every consumer (zero copy) and no consumer can corrupt it for the others.
* Copies happen on WRITE, not READ: one new value per change, shared by N readers.
* Editing is TYPED and FUNCTIONAL (no dicts): ``evolve()`` returns a new frozen
  value. Clean for collection add/remove and top-level fields; verbose only for
  deep nested scalars (shown so you can judge the cost).

In-place ``draft.a.b.c = x`` editing is NOT available on a frozen tree (Pydantic
frozen is class-level and can't be thawed in place); that would need mutable
"draft twin" classes (Immer-style). This shows the frozen-native path.
"""

import time
from collections.abc import Callable
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError


class Frozen(BaseModel):
    """Base for the immutable tree: frozen (hashable, value-equality, no reassignment)."""

    model_config = ConfigDict(frozen=True)

    def evolve(self, **changes: object) -> Self:
        """Typed functional update — a new frozen instance with ``changes`` applied.

        Shallow by design: unchanged subtrees are shared by reference (safe because
        they're frozen), so only the edited path allocates. (model_copy(update=)
        skips validation; re-validate at the Document boundary if range matters.)
        """
        return self.model_copy(update=changes)


class Mosaic(Frozen):
    overlap_x: float = 0.1
    overlap_y: float = 0.1


class Stencil(Frozen):
    mosaic: Mosaic = Mosaic()


class Task(Frozen):
    name: str
    x: float
    y: float


class State(Frozen):
    stencil: Stencil = Stencil()
    tasks: tuple[Task, ...] = ()  # tuple, not dict/list: frozen doesn't protect mutable containers

    # The deep `evolve` chains live HERE, once, as named domain operations — never at
    # call sites. This doubles as the typed, testable vocabulary of valid edits.
    def with_overlap(self, x: float) -> "State":
        return self.evolve(stencil=self.stencil.evolve(mosaic=self.stencil.mosaic.evolve(overlap_x=x)))

    def add_task(self, task: Task) -> "State":
        return self.evolve(tasks=(*self.tasks, task))

    def remove_task(self, name: str) -> "State":
        return self.evolve(tasks=tuple(t for t in self.tasks if t.name != name))


class Document[T: BaseModel]:
    """Owns one immutable value. Reads are zero-copy; a change notifies every
    consumer with the SAME new reference (safe to share because it's frozen)."""

    def __init__(self, value: T) -> None:
        self._value = value
        self._version = 0
        self._subs: list[Callable[[int, T], None]] = []

    @property
    def value(self) -> T:
        """Zero-copy read: return the live frozen reference."""
        return self._value

    @property
    def version(self) -> int:
        return self._version

    def subscribe(self, cb: Callable[[int, T], None]) -> Callable[[], None]:
        self._subs.append(cb)
        return lambda: self._subs.remove(cb)

    def set(self, value: T) -> None:
        """Swap in a new (already-frozen) value and notify everyone with it."""
        if value == self._value:  # value-equality on frozen models — free no-op detection
            return
        self._value = value
        self._version += 1
        for cb in self._subs:
            cb(self._version, value)


class TaskCount:
    """A 'computed' needing ONE field: reads off the pushed value — no snapshot, no copy."""

    def __init__(self, doc: Document[State]) -> None:
        self.value = len(doc.value.tasks)
        doc.subscribe(self._on_change)

    def _on_change(self, _version: int, state: State) -> None:
        self.value = len(state.tasks)  # reads the shared frozen ref directly


def main() -> None:
    doc: Document[State] = Document(State())
    count = TaskCount(doc)

    def on_change(v: int, s: State) -> None:
        print(f"  emit → v{v}: overlap_x={s.stencil.mosaic.overlap_x}, tasks={[t.name for t in s.tasks]}")

    doc.subscribe(on_change)

    print("1. SHARING: every consumer sees the same object — zero per-consumer copies:")
    print(f"   doc.value is doc.value  ->  {doc.value is doc.value}")

    print("\n2. safe to share because frozen — a consumer cannot corrupt it for others:")
    field = "overlap_x"  # via a variable so the demo of an illegal write isn't a static type error
    try:
        setattr(doc.value.stencil.mosaic, field, 0.9)
    except ValidationError as e:
        print(f"   mutate the shared value  ->  {e.errors()[0]['type']}")

    print("\n3-5. TYPED edits via named operations — call sites stay one clean line each:")
    doc.set(doc.value.add_task(Task(name="s1", x=1.0, y=2.0)))
    doc.set(doc.value.remove_task("s1"))
    doc.set(doc.value.with_overlap(0.25))  # the deep one — but the nesting lives in State, not here

    print(f"\n   the one-field 'computed' tracked along with no snapshots: TaskCount.value = {count.value}")

    # Timing: shared zero-copy read vs today's deep-copy-per-read.
    big = State(tasks=tuple(Task(name=f"t{i}", x=float(i), y=0.0) for i in range(1000)))
    big_doc: Document[State] = Document(big)
    n = 2000

    t0 = time.perf_counter()
    for _ in range(n):
        _ = big_doc.value
    shared = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        big.model_copy(deep=True)
    copied = (time.perf_counter() - t0) / n * 1e6

    print("\n6. read cost @ 1000 tasks, per read:")
    print(f"   shared frozen reference: {shared:9.4f} µs")
    print(f"   deep copy (today):       {copied:9.4f} µs")
    print(f"   → 50 consumers per change: {shared * 50:.2f} µs vs {copied * 50:,.0f} µs")


if __name__ == "__main__":
    main()

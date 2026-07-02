"""Reactive primitives: Signal (events), Cell (values), Computed (multi-trigger), Derived (mapped).

Class hierarchy:

* :class:`Subscribable` — shared base. Holds subscribers, dispatches emissions.
  Not typically instantiated directly; use one of the subclasses below.
* :class:`Signal` — push-only event stream with a public ``emit``. Use for
  discrete events that don't carry a persistent value.
* :class:`Cell` — carries a current value. ``.value`` to read, ``.set(v)`` to
  update; emits to subscribers only on actual change.
* :class:`Computed` — read-only value recomputed when any of its explicit
  ``triggers`` emit; the function reads whatever state it needs. Emits on change.
* :class:`ReactiveQuery` — async query recomputed explicitly via ``get`` and
  refreshed in the background when triggers emit. Emits completed changed values.
* :class:`Derived` — read-only value mapped from a single source value via a
  function. Emits on change. A single-source convenience over :class:`Computed`.

Signal, Cell, Computed, and Derived all inherit from :class:`Subscribable`, so any
of them is a valid ``Subscribable[T]`` input wherever "something I can subscribe
to" is the contract (e.g., ``Computed.triggers``).

All handle sync OR async callbacks transparently. Callback exceptions are
logged and never propagate up — one bad subscriber doesn't poison the others.
"""

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from vxlib.types import UNSET, Teardown, UnsetType

log = logging.getLogger(__name__)

type Listener[T] = Callable[[T], Awaitable[None] | None]


class Subscribable[T]:
    def __init__(self) -> None:
        self._subs: list[Listener[T]] = []

    def subscribe(self, cb: Listener[T]) -> Teardown:
        """Register ``cb`` and return an unsubscribe callable."""
        self._subs.append(cb)
        return lambda: self._unsubscribe(cb)

    async def _notify(self, value: T) -> None:
        """Invoke every subscriber with ``value``. Awaits async callbacks."""
        for cb in list(self._subs):
            try:
                result = cb(value)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception("Error in %s subscriber", type(self).__name__)

    def _unsubscribe(self, cb: Listener[T]) -> None:
        with contextlib.suppress(ValueError):
            self._subs.remove(cb)

    @property
    def subs(self) -> int:
        """Number of active subscribers."""
        return len(self._subs)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(subs={len(self._subs)})"


class Emitter[T](Subscribable[T]):
    """Typed push-only event stream. See module docstring."""

    async def emit(self, value: T) -> None:
        """Invoke every subscriber with ``value``. Awaits async callbacks."""
        await self._notify(value)


class Readable[T](Protocol):
    """A subscribable that also carries a current value (Cell, Computed, Derived)."""

    @property
    def value(self) -> T: ...

    def subscribe(self, cb: Listener[T]) -> Teardown: ...


class ReadableView[T]:
    """Read-only runtime view over a readable source."""

    def __init__(self, source: Readable[T]) -> None:
        self._source = source

    @property
    def value(self) -> T:
        """Current source value."""
        return self._source.value

    def subscribe(self, cb: Listener[T]) -> Teardown:
        """Register ``cb`` on the source and return an unsubscribe callable."""
        return self._source.subscribe(cb)

    def __repr__(self) -> str:
        return f"ReadableView({self._source!r})"


class Cell[T](Subscribable[T]):
    """Push-pull value cell: a :class:`Subscribable` that also carries a current value.

    Caches its current value and dedupes emissions — setting a new value via
    :meth:`set` emits to subscribers only if the new value differs from the
    current one.

    This is the observer-pattern equivalent of Svelte's ``$state`` or Vue's
    ``ref`` — useful when the *value itself* is the API (e.g., a hardware
    property that changes over time and many consumers read its current value
    plus react to changes).

    For discrete "something happened" events where consumers re-query fresh
    state, prefer :class:`Signal` instead.

    Typical use::

        class Camera:
            exposure: Cell[float] = Cell(0.01)


        # Consumer: read current value
        current = camera.exposure.value

        # Consumer: react to future changes
        unsub = camera.exposure.subscribe(lambda ms: print(f"exposure → {ms}"))

        # Producer: set (emits only if changed)
        await camera.exposure.set(0.02)
    """

    def __init__(self, initial: T) -> None:
        super().__init__()
        self._value = initial

    @property
    def value(self) -> T:
        """Current value."""
        return self._value

    async def set(self, new: T) -> None:
        """Update the value. Emits to subscribers only if ``new != current``."""
        if new != self._value:
            self._value = new
            await self._notify(new)

    def __repr__(self) -> str:
        return f"Cell({self._value!r}, subs={len(self._subs)})"


class Computed[T](Subscribable[T]):
    """Read-only value recomputed when any of its explicit triggers emit.

    Emits to its own subscribers only if the recomputed value differs from the
    previous one (equality-skip, same as :class:`Cell`). With no ``triggers``,
    recompute on demand via :meth:`refresh`.

    Triggers are declared explicitly — no auto-tracking — which keeps the
    implementation simple and the trigger graph legible at the call site. Any
    :class:`Subscribable` is a valid trigger (Signal, Cell, Computed, or Derived);
    ``fn`` reads whatever state it needs. For a pure map of a single source value,
    prefer :class:`Derived`.

    Typical use::

        preview_running = Cell[bool](False)
        acq_running = Cell[bool](False)

        mode = Computed[SessionMode](
            preview_running,
            acq_running,
            fn=lambda: (
                SessionMode.ACQUIRING
                if acq_running.value
                else SessionMode.PREVIEWING
                if preview_running.value
                else SessionMode.IDLE
            ),
        )

        # Consumer: read current
        current = mode.value

        # Consumer: react to changes
        mode.subscribe(lambda m: print(f"mode → {m}"))
    """

    def __init__(self, *triggers: Subscribable[Any], fn: Callable[[], T]) -> None:
        super().__init__()
        self._fn = fn
        self._value: T = fn()
        self._unsubs: list[Teardown] = [trigger.subscribe(lambda _: self.refresh()) for trigger in triggers]

    async def refresh(self) -> None:
        """Recompute now; emit if the value changed."""
        new = self._fn()
        if new != self._value:
            self._value = new
            await self._notify(new)

    @property
    def value(self) -> T:
        """Current computed value."""
        return self._value

    def close(self) -> None:
        """Detach from all triggers. Idempotent."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    def __repr__(self) -> str:
        return f"Computed({self._value!r}, subs={len(self._subs)})"


class ReactiveQuery[T](Subscribable[T]):
    """Async derived query with explicit fresh reads and trigger-driven refreshes.

    Call :meth:`get` to recompute now and read a guaranteed-fresh value. The last
    completed result is exposed via :attr:`cache` for synchronous consumers that
    need the most recent value without awaiting (e.g. assembling a snapshot in a
    sync callback); it may be stale relative to the underlying state and is ``None``
    until the first completed compute. Trigger emissions schedule coalesced
    background recomputes and notify subscribers when the completed value changes.
    """

    def __init__(self, *triggers: Subscribable[Any], fn: Callable[[], Awaitable[T]]) -> None:
        super().__init__()
        self._fn = fn
        self._value: T | UnsetType = UNSET
        self._lock = asyncio.Lock()
        self._dirty = False
        self._closed = False
        self._task: asyncio.Task[None] | None = None
        self._unsubs: list[Teardown] = []
        self.add_triggers(*triggers)

    @property
    def cache(self) -> T | None:
        """Last completed value (may be stale); ``None`` until the first compute."""
        return None if isinstance(self._value, UnsetType) else self._value

    async def get(self) -> T:
        """Recompute now; emit if the completed value changed; return the fresh value."""
        async with self._lock:
            new = await self._fn()
            current = self._value
            if current is UNSET or new != current:
                self._value = new
                await self._notify(new)
            return new

    def add_trigger(self, trigger: Subscribable[Any]) -> Teardown:
        """Subscribe to one trigger and return a teardown for that trigger."""
        if self._closed:
            raise RuntimeError(f"{type(self).__name__} is closed")
        unsub = trigger.subscribe(self._on_trigger)
        active = True

        def teardown() -> None:
            nonlocal active
            if not active:
                return
            active = False
            unsub()
            with contextlib.suppress(ValueError):
                self._unsubs.remove(teardown)

        self._unsubs.append(teardown)
        return teardown

    def add_triggers(self, *triggers: Subscribable[Any]) -> list[Teardown]:
        """Subscribe to multiple triggers and return their teardowns."""
        return [self.add_trigger(trigger) for trigger in triggers]

    def clear_triggers(self) -> None:
        """Detach all triggers and cancel any pending background refresh. Idempotent."""
        for unsub in list(self._unsubs):
            unsub()
        self._unsubs = []
        self._dirty = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def close(self) -> None:
        """Detach from triggers and cancel any pending background refresh. Idempotent."""
        self._closed = True
        self.clear_triggers()

    def _on_trigger(self, _value: Any) -> None:
        if self._closed:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            while self._dirty and not self._closed:
                self._dirty = False
                await self.get()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error refreshing %s", type(self).__name__)

    def __repr__(self) -> str:
        return f"ReactiveQuery(cached={self._value is not UNSET}, subs={len(self._subs)})"


class Derived[S, T](Subscribable[T]):
    """Read-only value mapped from a single source by a pure function.

    Holds ``fn(source.value)`` and refreshes when ``source`` emits, re-emitting only
    on actual change. Unlike :class:`Cell` it has no ``set`` — its value is owned by
    the source. For multiple triggers or reading extra state, use :class:`Computed`.

    Typical use::

        exposure_ms = Cell[float](10.0)
        exposure_s = Derived(exposure_ms, fn=lambda ms: ms / 1000)
    """

    def __init__(self, source: Readable[S], *, fn: Callable[[S], T]) -> None:
        super().__init__()
        self._fn = fn
        self._value: T = fn(source.value)
        self._unsub = source.subscribe(self._update)

    async def _update(self, value: S) -> None:
        new = self._fn(value)
        if new != self._value:
            self._value = new
            await self._notify(new)

    @property
    def value(self) -> T:
        """Current derived value."""
        return self._value

    def close(self) -> None:
        """Detach from the source. Idempotent."""
        self._unsub()

    def __repr__(self) -> str:
        return f"Derived({self._value!r}, subs={len(self._subs)})"

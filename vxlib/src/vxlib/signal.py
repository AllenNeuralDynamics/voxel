"""Reactive primitives: Signal (events), Cell (values), Sink (coalesced async drain).

Three small classes covering distinct roles:

* :class:`Signal` — push-only event stream. Multiple subscribers; every emit delivered.
* :class:`Cell` — value that subscribers can read AND watch. Multiple subscribers;
  every change delivered (with equality-skip).
* :class:`Sink` — sync producer → async drain bridge with latest-wins (or fold)
  semantics. Single drain, configured at construction. Drops intermediate puts
  when the drain is slow.

All three handle sync OR async callbacks transparently. Callback exceptions are
logged and never propagate up — one bad subscriber doesn't poison the others.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

type Listener[T] = Callable[[T], Awaitable[None] | None]
type Unsub = Callable[[], None]


class Signal[T]:
    """Typed push-only event stream. See module docstring."""

    def __init__(self) -> None:
        self._subs: list[Listener[T]] = []

    def subscribe(self, cb: Listener[T]) -> Unsub:
        """Register ``cb`` and return an unsubscribe callable."""
        self._subs.append(cb)
        return lambda: self._unsubscribe(cb)

    def _unsubscribe(self, cb: Listener[T]) -> None:
        try:
            self._subs.remove(cb)
        except ValueError:
            pass  # already unsubscribed; idempotent

    async def emit(self, value: T) -> None:
        """Invoke every subscriber with ``value``. Awaits async callbacks."""
        for cb in list(self._subs):
            try:
                result = cb(value)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception("Error in Signal subscriber")

    def __len__(self) -> int:
        return len(self._subs)


class Cell[T]:
    """Push-pull value cell: holds a value AND notifies on change.

    Unlike ``Signal[T]`` (push-only event stream), a ``Cell[T]`` carries a
    current value that subscribers can read at any time. Setting a new value
    via :meth:`set` emits only if the new value differs from the current one.

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
        self._value = initial
        self._changed = Signal[T]()

    @property
    def value(self) -> T:
        """Current value."""
        return self._value

    async def set(self, new: T) -> None:
        """Update the value. Emits to subscribers only if ``new != current``."""
        if new != self._value:
            self._value = new
            await self._changed.emit(new)

    def subscribe(self, cb: Listener[T]) -> Unsub:
        """Register ``cb`` to be invoked on future value changes."""
        return self._changed.subscribe(cb)

    def __len__(self) -> int:
        return len(self._changed)


class Sink[T]:
    """Sync→async receiver with latest-wins (or fold) semantics. Lossy by design.

    A ``Sink[T]`` accepts sync :meth:`put` at any rate; a background task drains
    received values to the ``drain`` callback whenever it's ready. Values produced
    faster than the drain consumes are **silently overwritten** — the sink carries
    freshness, not completeness. For lossless FIFO delivery, use a different
    primitive (e.g. ``asyncio.Queue``); ``Sink`` is the wrong tool for "every
    value matters."

    Optional ``reducer`` folds rapid puts together instead of overwriting,
    preserving partial-update information across keys::

        sink = Sink[dict[str, Levels]](drain=send_levels, reducer=merge_dicts)
        sink.put({"ch1": l1})  # stored
        sink.put({"ch2": l2})  # folded → {"ch1": l1, "ch2": l2}

    Lazy-starts the delivery task on first ``put``. Re-startable after
    :meth:`close` — next ``put`` spins up a new task.

    Intentionally 1:1 (one producer side, one drain). For multi-observer
    broadcast, use :class:`Signal` or :class:`Cell`; ``Sink`` is a bridge,
    not a broadcaster.
    """

    def __init__(
        self,
        drain: Listener[T],
        *,
        reducer: Callable[[T, T], T] | None = None,
    ) -> None:
        self._drain = drain
        self._reducer = reducer
        self._value: T | None = None
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def put(self, value: T) -> None:
        """Submit a value. Sync, never blocks.

        Older unused values are overwritten (or folded via ``reducer``). Lazy-starts
        the delivery task if not already running.
        """
        if self._reducer is not None and self._value is not None:
            self._value = self._reducer(self._value, value)
        else:
            self._value = value
        self._event.set()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def close(self) -> None:
        """Cancel the delivery task. Sync. Idempotent. Safe to call from any context.

        The next :meth:`put` will lazy-start a fresh task — close is a stop, not a
        permanent shutdown. Pending value (if any) is discarded.
        """
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None
        self._value = None
        self._event.clear()

    async def _run(self) -> None:
        try:
            while True:
                await self._event.wait()
                self._event.clear()
                if self._value is None:
                    continue
                value, self._value = self._value, None
                try:
                    result = self._drain(value)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    log.exception("Sink drain failed")
        except asyncio.CancelledError:
            return

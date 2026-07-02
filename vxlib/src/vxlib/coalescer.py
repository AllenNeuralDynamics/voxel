"""Coalescer: a lossy sync→async bridge.

A ``Coalescer[T]`` takes sync ``put`` at any rate and drains the latest value to an async
callback when ready — overwriting (or folding via a reducer) values produced faster
than the drain consumes. It is 1:1 (one drain, not a broadcaster) and standalone; for
multi-observer broadcast use ``Signal`` or ``Cell`` from :mod:`vxlib.reactivity`.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

type Drain[T] = Callable[[T], Awaitable[None] | None]


class Coalescer[T]:
    """Sync→async receiver with latest-wins (or fold) semantics. Lossy by design.

    A ``Coalescer[T]`` accepts sync :meth:`put` at any rate; a background task drains
    received values to the ``drain`` callback whenever it's ready. Values produced
    faster than the drain consumes are **silently overwritten** — the coalescer carries
    freshness, not completeness. For lossless FIFO delivery, use a different
    primitive (e.g. ``asyncio.Queue``); ``Coalescer`` is the wrong tool for "every
    value matters."

    Optional ``reducer`` folds rapid puts together instead of overwriting,
    preserving partial-update information across keys::

        coalescer = Coalescer[dict[str, Levels]](drain=send_levels, reducer=merge_dicts)
        coalescer.put({"ch1": l1})  # stored
        coalescer.put({"ch2": l2})  # folded → {"ch1": l1, "ch2": l2}

    Lazy-starts the delivery task on first ``put``. Re-startable after
    :meth:`close` — next ``put`` spins up a new task.

    Intentionally 1:1 (one producer side, one drain). For multi-observer
    broadcast, use :class:`Signal` or :class:`Cell`; ``Coalescer`` is a bridge,
    not a broadcaster.
    """

    def __init__(
        self,
        drain: Drain[T],
        *,
        reducer: Callable[[T, T], T] | None = None,
    ) -> None:
        self._drain = drain
        self._reducer = reducer
        self._value: T | None = None
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def update(self, value: T) -> None:
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

    def cancel(self) -> None:
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
                    log.exception("Coalescer drain failed")
        except asyncio.CancelledError:
            return

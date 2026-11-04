"""Sync facade for the one_liner router: every public coroutine of ``SeqSweep`` becomes a blocking method."""

import functools
import inspect
from collections.abc import Callable, Coroutine
from typing import Any

from seqsweep.seqsweep import SeqSweep

from .loop_thread import LoopThread


class SeqSweepRpc:
    """Serve this object on the router instead of ``SeqSweep``.

    The router calls plain functions on one thread and pickles what they return, so it cannot serve
    ``async def`` methods. For each public coroutine of ``SeqSweep`` this makes a sync twin with the same name,
    signature and docstring (the router builds its RPC schema from them) that runs it on the loop thread.
    Served methods must return quickly: start background work and return, never wait out a whole scan.
    """

    def __init__(self, seqsweep: SeqSweep) -> None:
        self._seqsweep = seqsweep
        self._loop = LoopThread()
        for name, method in inspect.getmembers(seqsweep, inspect.iscoroutinefunction):
            if not name.startswith("_") and not hasattr(type(self), name):
                print(f"Bridging method: {name}, signature: {inspect.signature(method)}")
                setattr(self, name, self._bridge(method))

    def _bridge(self, method: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
        @functools.wraps(method)  # method is bound, so the signature has no ``self``
        def call(*args: Any, **kwargs: Any) -> Any:
            return self._loop.run(method(*args, **kwargs))

        return call

    def open(self) -> None:
        """Open the rig. Raises ``HALStartupError`` if a device fails to build or fills the wrong role."""
        try:
            self._loop.run(self._seqsweep.open())
        except BaseException:
            self._loop.stop()
            raise

    def close(self) -> None:
        """Close the rig and stop the loop thread. Safe to call more than once."""
        if not self._loop.running:
            return
        try:
            self._loop.run(self._seqsweep.close())
        finally:
            self._loop.stop()

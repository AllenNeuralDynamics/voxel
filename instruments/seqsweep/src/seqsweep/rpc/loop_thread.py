"""An event loop on its own thread, so sync code (the one_liner router) can drive async code (the HAL)."""

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any


class LoopThread:
    """One event loop that lives as long as the server; every hardware call runs on it."""

    def __init__(self, name: str = "seqsweep-loop") -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name=name, daemon=True)
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread.is_alive() and not self._loop.is_closed()

    def submit[T](self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        """Start ``coro`` on the loop and return at once."""
        if not self.running:
            coro.close()
            raise RuntimeError("loop thread is stopped")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        """Run ``coro`` on the loop and block until it finishes; re-raises its exception."""
        return self.submit(coro).result()

    def stop(self) -> None:
        """Stop the loop and join the thread. Safe to call more than once."""
        if not self.running:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

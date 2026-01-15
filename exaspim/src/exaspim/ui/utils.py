"""UI utilities for async operations and Qt integration."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

log = logging.getLogger(__name__)


def run_async(
    coro: Coroutine[Any, Any, T],
    on_success: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> asyncio.Task[T]:
    """Fire-and-forget async call with optional callbacks.

    This helper is designed for use in Qt slots where you need to trigger
    an async operation. It requires qasync event loop to be running.

    Args:
        coro: The coroutine to execute
        on_success: Optional callback with the result
        on_error: Optional callback with the exception

    Returns:
        The created task (can be used for cancellation)

    Example:
        def _on_enable_clicked(self):
            run_async(
                self._handle.call("enable"),
                on_success=lambda r: self.log.info(f"Enabled: {r}"),
                on_error=self._show_error,
            )
    """
    task = asyncio.create_task(coro)

    def _done_callback(t: asyncio.Task[T]) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return  # Task was cancelled, not an error
        if exc is not None:
            if on_error and isinstance(exc, Exception):
                on_error(exc)
            else:
                log.exception("Unhandled error in async task", exc_info=exc)
        elif on_success:
            on_success(t.result())

    task.add_done_callback(_done_callback)
    return task


def run_async_silent(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Fire-and-forget async call that logs errors silently.

    Use this for operations where failure is non-critical.

    Args:
        coro: The coroutine to execute

    Returns:
        The created task
    """
    return run_async(coro, on_error=lambda e: log.warning(f"Async operation failed: {e}"))

"""Focused helpers for scheduling asyncio work."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

_log = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task[Any]] = set()


def spawn[T](
    coro: Coroutine[Any, Any, T],
    *,
    name: str | None = None,
    log: logging.Logger | None = None,
    timeout: float | None = None,
) -> asyncio.Task[T]:
    """Schedule a coroutine and retain its task until completion.

    The returned task may be awaited, cancelled, or ignored. Exceptions are
    logged on completion so ignored tasks do not fail silently. A task is held
    strongly until it completes, after which it is removed from the background
    set.

    Args:
        coro: The coroutine to run.
        name: Optional name for the task (for debugging).
        log: Optional logger to use. Defaults to the module logger.
        timeout: Maximum seconds the task may run before being cancelled.
            ``None`` disables the timeout.

    Returns:
        The created task.
    """
    logger = log or _log

    async def _with_timeout() -> T:
        async with asyncio.timeout(timeout):
            return await coro

    def handle_completion(task: asyncio.Task[T]) -> None:
        _background_tasks.discard(task)
        if task.cancelled():
            return
        if exc := task.exception():
            if isinstance(exc, TimeoutError):
                logger.warning("Background task %s timed out after %ss", task.get_name(), timeout)
            else:
                logger.error("Background task %s failed", task.get_name(), exc_info=exc)

    wrapped = _with_timeout() if timeout is not None else coro
    task = asyncio.create_task(wrapped, name=name)
    _background_tasks.add(task)
    task.add_done_callback(handle_completion)
    return task


__all__ = ["spawn"]

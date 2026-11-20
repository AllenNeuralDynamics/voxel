"""Focused helpers for scheduling asyncio work."""

import asyncio
import logging
from collections.abc import Awaitable, Coroutine, Iterable
from typing import Any, cast

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


async def gather_all[T](*calls: Awaitable[T], message: str) -> list[T]:
    """Wait for every call to end, even when some fail, and give back their results in order. Raise 1
    ``BaseExceptionGroup`` titled ``message`` with every failure. Unlike ``asyncio.TaskGroup``, a failure does not
    cancel the other calls, so no call is left half done."""
    results = await asyncio.gather(*calls, return_exceptions=True)
    if errors := [result for result in results if isinstance(result, BaseException)]:
        raise BaseExceptionGroup(message, errors)
    return cast("list[T]", results)


async def gather_in_order(steps: Iterable[tuple[Iterable[Awaitable[object]], str]], message: str) -> None:
    """Gather each step's calls with :func:`gather_all`, 1 step after the other; each pair is the calls and the step's
    title. Every step runs even when one fails. Raise 1 ``BaseExceptionGroup`` titled ``message`` with each failed
    step's group."""
    failures: list[BaseException] = []
    for calls, title in steps:
        try:
            await gather_all(*calls, message=title)
        except BaseExceptionGroup as group:
            failures.append(group)
    if failures:
        raise BaseExceptionGroup(message, failures)

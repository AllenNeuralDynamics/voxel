"""Shared utilities for voxel packages."""

import asyncio
import logging
import re
import socket
import threading
from collections.abc import Callable, Coroutine
from datetime import datetime
from functools import wraps
from typing import Any, cast

_log = logging.getLogger(__name__)


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time string."""
    now = datetime.now()
    delta = now - dt

    if delta.days == 0:
        if delta.seconds < 60:
            return "just now"
        if delta.seconds < 3600:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        hours = delta.seconds // 3600
        return f"{hours}h ago"
    if delta.days == 1:
        return "yesterday"
    if delta.days < 7:
        return f"{delta.days}d ago"
    return dt.strftime("%b %d")


def slugify(name: str) -> str:
    """Convert a display name to a filesystem-friendly slug."""
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def display_name(name: str, replacements: dict[str, str] | None = None) -> str:
    """Format session name for display.

    Args:
        name: The name to format.
        replacements: Characters to replace (key=old, value=new).
            Merged with defaults: {"-": " ", "_": " "}.
    """
    chars = {"-": " ", "_": " "}
    if replacements:
        chars.update(replacements)

    for old, new in chars.items():
        name = name.replace(old, new)

    return name.title()


def thread_safe_singleton[T](func: Callable[..., T]) -> Callable[..., T]:
    """A decorator that makes a function a thread-safe singleton.

    The decorated function will only be executed once, and its result
    will be cached and returned for all subsequent calls.
    """
    lock = threading.Lock()
    instance: T | None = None

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = func(*args, **kwargs)
        return cast("T", instance)

    return wrapper


def fire_and_forget(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
    log: logging.Logger | None = None,
    timeout: float | None = None,
) -> asyncio.Task:
    """Create a fire-and-forget task with automatic exception logging.

    Use this instead of bare `asyncio.create_task()` for background tasks
    where you don't need to await the result. Exceptions are logged
    automatically instead of being silently ignored.

    Args:
        coro: The coroutine to run.
        name: Optional name for the task (for debugging).
        log: Optional logger to use. Defaults to vxlib.utils logger.
        timeout: Maximum seconds the task may run before being cancelled.
            Defaults to 10s. Pass None to disable.

    Returns:
        The created task (stored reference prevents garbage collection).
    """
    logger = log or _log

    async def _with_timeout() -> None:
        async with asyncio.timeout(timeout):
            await coro

    def handle_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        if exc := task.exception():
            if isinstance(exc, TimeoutError):
                logger.warning("Background task %s timed out after %ss", task.get_name(), timeout)
            else:
                logger.error("Background task %s failed", task.get_name(), exc_info=exc)

    wrapped = _with_timeout() if timeout is not None else coro
    task = asyncio.create_task(wrapped, name=name)
    task.add_done_callback(handle_exception)
    return task


class CoalescedFlush[T]:
    """Background task that coalesces rapid updates of type T into batched flushes.

    Each ``put()`` stores a pending value and signals the flush loop. Rapid
    calls between flushes are coalesced — the flush callback receives only
    the latest (or merged) value.

    An optional *reducer* controls how successive puts combine:
    - Without reducer (default): latest value wins.
    - With reducer: ``value = reducer(old, new)`` on each put.

    Usage::

        # Scalar — latest wins
        vp_flush = CoalescedFlush[Viewport]()
        vp_flush.start(send_viewport)
        vp_flush.put(vp1)  # queued
        vp_flush.put(vp2)  # replaces vp1

        # Dict — merge across puts
        lvl_flush = CoalescedFlush[dict[str, Levels]](reducer=lambda o, n: {**o, **n})
        lvl_flush.start(send_levels)
        lvl_flush.put({"ch1": l1})  # queued
        lvl_flush.put({"ch2": l2})  # merged → {"ch1": l1, "ch2": l2}
    """

    def __init__(self, *, reducer: Callable[[T, T], T] | None = None) -> None:
        self._reducer = reducer
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._flush: Callable[[T], Coroutine[Any, Any, None]] | None = None
        self._value: T | None = None

    def start(self, flush: Callable[[T], Coroutine[Any, Any, None]]) -> None:
        """Start the background flush loop with the given callback."""
        self._flush = flush
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Stop the flush loop and discard pending value."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        self._value = None
        self._event.clear()

    def put(self, value: T) -> None:
        """Store a pending value and signal flush. Applies reducer if set."""
        if self._reducer is not None and self._value is not None:
            self._value = self._reducer(self._value, value)
        else:
            self._value = value
        self._event.set()

    async def _loop(self) -> None:
        try:
            while True:
                await self._event.wait()
                self._event.clear()
                if self._flush and self._value is not None:
                    value = self._value
                    self._value = None
                    await self._flush(value)
        except asyncio.CancelledError:
            return


def merge_dicts[K, V](old: dict[K, V], new: dict[K, V]) -> dict[K, V]:
    """Reducer for CoalescedFlush that merges dicts (new entries override old)."""
    return {**old, **new}


def get_local_ip() -> str:
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

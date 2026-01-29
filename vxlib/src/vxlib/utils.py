"""Shared utilities for voxel packages."""

import asyncio
import logging
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
) -> asyncio.Task:
    """Create a fire-and-forget task with automatic exception logging.

    Use this instead of bare `asyncio.create_task()` for background tasks
    where you don't need to await the result. Exceptions are logged
    automatically instead of being silently ignored.

    Args:
        coro: The coroutine to run.
        name: Optional name for the task (for debugging).
        log: Optional logger to use. Defaults to vxlib.utils logger.

    Returns:
        The created task (stored reference prevents garbage collection).
    """
    logger = log or _log

    def handle_exception(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        if exc := task.exception():
            logger.error("Background task %s failed", task.get_name(), exc_info=exc)

    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(handle_exception)
    return task


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

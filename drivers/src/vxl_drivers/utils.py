"""Utilities shared by Voxel hardware drivers."""

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, cast


def thread_safe_singleton[T](func: Callable[..., T]) -> Callable[..., T]:
    """Cache exactly one result from a function across concurrent callers."""
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


__all__ = ["thread_safe_singleton"]

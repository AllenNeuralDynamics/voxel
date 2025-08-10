from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any, TypeVar, cast, ClassVar

T = TypeVar("T")


def thread_safe_singleton(func: Callable[..., T]) -> Callable[..., T]:
    """
    A decorator that makes a function a thread-safe singleton.
    The decorated function will only be executed once, and its result
    will be cached and returned for all subsequent calls.

    :param func: The function to be decorated.
    :type func: function
    :return: The singleton instance of the function.
    :rtype: function
    """
    lock = Lock()
    instance: T | None = None

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        """
        Wrapper function to ensure thread-safe singleton behavior.

        :return: The singleton instance of the function.
        :rtype: function
        """
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = func(*args, **kwargs)
        return instance

    return wrapper


TSingleton = TypeVar("TSingleton", bound="Singleton")


class Singleton(type):
    """
    Thread-safe singleton metaclass.
    """

    _instances: ClassVar[dict[type[Any], Any]] = {}
    _lock: ClassVar[Lock] = Lock()

    def __call__(cls: type[TSingleton], *args: Any, **kwargs: Any) -> TSingleton:
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cast("TSingleton", cls._instances[cls])

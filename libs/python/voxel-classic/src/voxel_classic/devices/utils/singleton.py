from functools import wraps
from threading import Lock
from typing import Callable, Any, TypeVar, Type

T = TypeVar('T')


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
    instance: T = None

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


class Singleton(type):
    """
    This is a thread-safe implementation of Singleton.
    """

    _instances: dict[Type, Any] = {}

    _lock: Lock = Lock()
    """
    We now have a lock object that will be used to synchronize threads during
    first access to the Singleton.
    """

    def __call__(cls: Type[T], *args: Any, **kwargs: Any) -> T:
        """
        Ensure that only one instance of the class is created.

        :return: The singleton instance of the class.
        :rtype: object
        """
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]
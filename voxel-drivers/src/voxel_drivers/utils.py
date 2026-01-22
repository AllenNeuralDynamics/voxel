import threading
from functools import wraps


def thread_safe_singleton(func):
    """A decorator that makes a function a thread-safe singleton.
    The decorated function will only be executed once, and its result
    will be cached and returned for all subsequent calls.
    """
    lock = threading.Lock()
    instance = None

    @wraps(func)
    def wrapper(*args, **kwargs):
        nonlocal instance
        if instance is None:
            with lock:
                if instance is None:
                    instance = func(*args, **kwargs)
        return instance

    return wrapper

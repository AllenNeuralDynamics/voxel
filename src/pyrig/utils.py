import logging
import socket
from collections.abc import Sequence
from functools import wraps
from threading import Lock
from typing import Any

import zmq

try:
    from rich.logging import RichHandler
except ImportError:
    RichHandler = None  # type: ignore[assignment]


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


def thread_safe_singleton(func):
    """A decorator that makes a function a thread-safe singleton.
    The decorated function will only be executed once, and its result
    will be cached and returned for all subsequent calls.
    """
    lock = Lock()
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


def configure_logging(
    level=logging.INFO,
    fmt: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt: str = "[%X]",
    handlers: Sequence[logging.Handler] | None = None,
    *,
    rich_tracebacks: bool = True,
    rich_markup: bool = False,
) -> list[logging.Handler]:
    """Configure logging with optional Rich handler support.

    Args:
        level: Root logging level.
        fmt: Logging format string.
        datefmt: Date format passed to logging.
        handlers: Optional handler sequence. When omitted we try to add Rich if present.
        rich_tracebacks: Passed to RichHandler when auto-installed.
        rich_markup: Passed to RichHandler when auto-installed.

    Returns:
        List of handlers installed (empty if none were set explicitly).
    """

    resolved_handlers: list[logging.Handler] = []
    if handlers is None:
        if RichHandler is not None:
            resolved_handlers.append(RichHandler(rich_tracebacks=rich_tracebacks, markup=rich_markup))
            fmt = "%(name)s: %(message)s"
    else:
        resolved_handlers.extend(handlers)

    basic_kwargs: dict[str, Any] = {"level": level, "format": fmt, "datefmt": datefmt}
    if resolved_handlers:
        basic_kwargs["handlers"] = resolved_handlers

    logging.basicConfig(**basic_kwargs)
    return resolved_handlers


class ZmqTopicHandler(logging.Handler):
    """Publish log records via ZMQ using `<logger>.<LEVEL>` topics."""

    def __init__(self, address: str):
        super().__init__()
        self._ctx = zmq.Context()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.connect(address)

    def emit(self, record: logging.LogRecord) -> None:
        if self._socket is None:
            return
        logger_name = record.name or "root"
        topic = f"{logger_name}.{record.levelname}"
        try:
            message = self.format(record)
            self._socket.send_multipart(
                [
                    topic.encode("utf-8", errors="replace"),
                    message.encode("utf-8", errors="replace"),
                ]
            )
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._socket is not None:
                self._socket.close(0)
            if self._ctx is not None:
                self._ctx.term()
        finally:
            self._socket = None
            self._ctx = None
            super().close()


if RichHandler:

    class UvicornRichHandler(RichHandler):
        """RichHandler subclass that handles uvicorn's levelprefix format."""

        def format(self, record: logging.LogRecord) -> str:
            """Format the record, handling uvicorn's levelprefix."""
            # Remove levelprefix if present (uvicorn adds this)
            if hasattr(record, "levelprefix"):
                # Already has color prefix from uvicorn, just use the message
                return record.getMessage()
            return super().format(record)


def get_uvicorn_log_config(datefmt: str = "[%X]") -> dict[str, Any]:
    """Get uvicorn log configuration that works with RichHandler.

    When Rich is available, this configures uvicorn to use UvicornRichHandler
    which strips ANSI color codes from uvicorn's formatters to prevent double
    formatting (uvicorn's ANSI + Rich's formatting).

    When Rich is not available, returns None to use uvicorn's default config.

    Args:
        datefmt: Date format string (e.g., "[%X]" for time only, "%Y-%m-%d %H:%M:%S" for full)

    Returns:
        Log configuration dict for uvicorn, or None for defaults.
    """
    if not RichHandler:
        return None  # type: ignore[return-value]

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelname)s:     %(message)s",
                "datefmt": datefmt,
                "use_colors": False,  # Disable ANSI codes to prevent double-formatting
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": datefmt,
                "use_colors": False,  # Disable ANSI codes
            },
        },
        "handlers": {
            "default": {
                "class": "pyrig.utils.UvicornRichHandler",
                "rich_tracebacks": True,
                "markup": False,
                "formatter": "default",
            },
            "access": {
                "class": "pyrig.utils.UvicornRichHandler",
                "rich_tracebacks": True,
                "markup": False,
                "formatter": "access",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }

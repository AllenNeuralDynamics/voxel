from collections.abc import Sequence
import logging
import socket
from typing import Any


def configure_logging(
    level: int = logging.INFO,
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
        try:
            from rich.logging import RichHandler
        except ImportError:
            RichHandler = None  # type: ignore[assignment]
        if RichHandler is not None:
            resolved_handlers.append(RichHandler(rich_tracebacks=rich_tracebacks, markup=rich_markup))
    else:
        resolved_handlers.extend(handlers)

    basic_kwargs: dict[str, Any] = {"level": level, "format": fmt, "datefmt": datefmt}
    if resolved_handlers:
        basic_kwargs["handlers"] = resolved_handlers

    logging.basicConfig(**basic_kwargs)
    return resolved_handlers


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

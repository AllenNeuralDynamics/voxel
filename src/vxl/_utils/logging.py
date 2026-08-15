"""Shared logging utilities for voxel packages."""

import logging
from collections.abc import Sequence
from typing import Any

try:
    from rich.logging import RichHandler
except ImportError:
    RichHandler = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)

# Extra fields that the VxlRichHandler renders inline.
# Only explicitly known fields are shown — prevents uvicorn/third-party internals from leaking.
_EXTRA_FIELDS = ("action", "target", "tags", "node_id")


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
        if RichHandler is not None:
            resolved_handlers.append(VxlRichHandler(rich_tracebacks=rich_tracebacks, markup=rich_markup))
            fmt = "%(name)s: %(message)s"
    else:
        resolved_handlers.extend(handlers)

    basic_kwargs: dict[str, Any] = {"level": level, "format": fmt, "datefmt": datefmt}
    if resolved_handlers:
        basic_kwargs["handlers"] = resolved_handlers

    logging.basicConfig(**basic_kwargs)
    return resolved_handlers


if RichHandler:

    class VxlRichHandler(RichHandler):
        """RichHandler that renders extra fields inline and handles uvicorn's levelprefix."""

        def format(self, record: logging.LogRecord) -> str:
            # Handle uvicorn's levelprefix format
            if hasattr(record, "levelprefix"):
                return record.getMessage()

            base = super().format(record)

            # Render known extra fields
            extras = {k: getattr(record, k) for k in _EXTRA_FIELDS if getattr(record, k, None) is not None}
            if extras:
                parts = " ".join(f"{k}={v}" for k, v in extras.items())
                if record.getMessage():
                    return f"{base} :: {parts}"
                # Empty message — replace it with the extras
                return base.rstrip() + " " + parts
            return base


def get_uvicorn_log_config(datefmt: str = "[%X]", access_log_level: str = "WARNING") -> dict[str, Any]:
    """Get uvicorn log configuration that works with VxlRichHandler.

    When Rich is available, this configures uvicorn to use VxlRichHandler
    which strips ANSI color codes from uvicorn's formatters to prevent double
    formatting (uvicorn's ANSI + Rich's formatting).

    When Rich is not available, returns None to use uvicorn's default config.

    Args:
        datefmt: Date format string (e.g., "[%X]" for time only, "%Y-%m-%d %H:%M:%S" for full)
        access_log_level: Log level for access logs (default: "WARNING" to hide 200 OK logs)

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
                "use_colors": False,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
                "datefmt": datefmt,
                "use_colors": False,
            },
        },
        "handlers": {
            "default": {
                "class": f"{__name__}.VxlRichHandler",
                "rich_tracebacks": True,
                "markup": False,
                "formatter": "default",
            },
            "access": {
                "class": f"{__name__}.VxlRichHandler",
                "rich_tracebacks": True,
                "markup": False,
                "formatter": "access",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": access_log_level, "propagate": False},
        },
    }

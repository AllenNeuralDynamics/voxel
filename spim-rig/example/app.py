"""Run SPIM Rig web server with proper logging.

Usage:
    cd spim-rig
    uv run python example/app.py [system.yaml]
"""

import logging
import sys
from pathlib import Path

import uvicorn
from rich.logging import RichHandler

from pyrig.utils import configure_logging

# Configure logging first with RichHandler
rich_handlers = configure_logging(level=logging.INFO, fmt="%(message)s", datefmt="[%X]")
log = logging.getLogger("spim_rig.app")


class UvicornRichHandler(RichHandler):
    """RichHandler subclass that handles uvicorn's levelprefix format."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the record, handling uvicorn's levelprefix."""
        # Remove levelprefix if present (uvicorn adds this)
        if hasattr(record, "levelprefix"):
            # Already has color prefix from uvicorn, just use the message
            return record.getMessage()
        return super().format(record)


def main():
    """Entry point for SPIM rig web server."""

    # Determine config path
    if len(sys.argv) < 2:
        config_path = Path(__file__).parent / "system.yaml"
        log.warning("No config file provided. Using: %s", config_path)
    else:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        log.error("Config file not found: %s", config_path)
        sys.exit(1)

    log.info("Starting SPIM Rig web server with config: %s", config_path)

    # Create the app with the config path
    from spim_rig.web.app import create_app

    app = create_app(str(config_path))

    # Configure uvicorn to use RichHandler with consistent time format
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(message)s",  # Just message, no levelprefix (RichHandler adds its own)
                    "use_colors": False,  # Disable ANSI codes
                    "datefmt": "[%X]",
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(client_addr)s - "%(request_line)s" %(status_code)s',  # No levelprefix
                    "datefmt": "[%X]",
                },
            },
            "handlers": {
                "default": {
                    "class": "example.app.UvicornRichHandler",
                    "rich_tracebacks": True,
                    "markup": False,
                    "formatter": "default",
                },
                "access": {
                    "class": "example.app.UvicornRichHandler",
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
        },
    )


if __name__ == "__main__":
    main()

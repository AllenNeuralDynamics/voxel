"""Run SPIM Rig web server with proper logging.

Usage:
    cd spim-rig
    uv run python example/app.py [system.yaml]
"""

import logging
import sys
from pathlib import Path

import uvicorn

from pyrig.utils import configure_logging, get_uvicorn_log_config

# Configure logging first with RichHandler
configure_logging(level=logging.INFO, fmt="%(message)s", datefmt="[%X]")
log = logging.getLogger("spim_rig.app")


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
        log_config=get_uvicorn_log_config(),
    )


if __name__ == "__main__":
    main()

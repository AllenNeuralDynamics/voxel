"""CLI for Voxel Studio.

Examples:
    # Start in lobby mode (default)
    voxel

    # Start with debug logging
    voxel --debug

    # Start on a different port
    voxel --port 9000
"""

import argparse
import logging

import uvicorn
from pyrig.utils import configure_logging, get_local_ip, get_uvicorn_log_config
from voxel_studio.app import create_app


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="voxel",
        description="Voxel Studio - Microscope Control System",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def main() -> None:
    """Main entry point for voxel CLI."""
    parser = create_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("voxel")

    log.info("Starting Voxel Studio...")

    app = create_app()

    local_ip = get_local_ip()
    log.info("Web UI: http://localhost:%d", args.port)
    if local_ip != "127.0.0.1":
        log.info("      or http://%s:%d", local_ip, args.port)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_config=get_uvicorn_log_config(),
    )


if __name__ == "__main__":
    main()

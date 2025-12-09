"""CLI for SPIM Rig - Run rig controller or node services.

Examples:
    # Start rig controller
    spim rig system.yaml
    spim rig system.yaml --port 8080 --debug

    # Start node service
    spim node camera_1 --rig 192.168.1.100
    spim node daq_1 --rig localhost:9000 --debug
"""

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from pyrig.node import run_node_service
from pyrig.utils import configure_logging, get_local_ip, get_uvicorn_log_config
from spim_rig import SpimRigConfig
from spim_rig.node import SpimNodeService
from spim_rig.web import create_rig_app


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with rig and node subcommands."""
    parser = argparse.ArgumentParser(
        prog="spim",
        description="SPIM Rig Control System - Run rig controller or node services",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to run",
        required=True,
    )

    # RIG subcommand
    rig_parser = subparsers.add_parser(
        "rig",
        help="Start the rig controller with web server",
        description="Start the SPIM rig controller with web interface",
    )
    rig_parser.add_argument(
        "config_path",
        type=str,
        help="Path to YAML configuration file",
    )
    rig_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)",
    )
    rig_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    # NODE subcommand
    node_parser = subparsers.add_parser(
        "node",
        help="Start a node service",
        description="Start a SPIM node service to manage devices",
    )
    node_parser.add_argument(
        "node_id",
        type=str,
        help="Node identifier (e.g., camera_1, daq_1)",
    )
    node_parser.add_argument(
        "--rig",
        type=str,
        required=True,
        help="Rig controller address (host or host:port, default port: 9000)",
    )
    node_parser.add_argument(
        "--log-port",
        type=int,
        default=9001,
        help="Controller log port (default: 9001)",
    )
    node_parser.add_argument(
        "--start-port",
        type=int,
        default=10000,
        help="Starting port for device services (default: 10000)",
    )
    node_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser


def run_rig(args: argparse.Namespace) -> None:
    """Run the rig controller with web server.

    Args:
        args: Parsed arguments containing config_path, port, debug
    """
    # Configure logging based on debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("spim_rig.app")

    # Validate and load config file
    config_path = Path(args.config_path)
    if not config_path.exists():
        log.error("Config file not found: %s", config_path)
        sys.exit(1)

    log.info("Loading rig configuration from: %s", config_path.absolute())
    try:
        config = SpimRigConfig.from_yaml(str(config_path))
    except Exception as e:
        log.error("Failed to load config: %s", e)
        sys.exit(1)

    log.info("Starting SPIM Rig web server")

    # Create FastAPI app with loaded config
    app = create_rig_app(config)

    local_ip = get_local_ip()
    log.info("Web UI: http://localhost:%d", args.port)
    if local_ip != "127.0.0.1":
        log.info("      or http://%s:%d", local_ip, args.port)

    # Run with uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=args.port,
        log_config=get_uvicorn_log_config(),
    )


def run_node(args: argparse.Namespace) -> None:
    """Run a node service.

    Args:
        args: Parsed arguments containing node_id, rig, log_port, start_port, debug
    """
    # Configure logging based on debug flag
    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("spim_rig.app")

    # Parse host:port from --rig argument
    if ":" in args.rig:
        ctrl_host, port_str = args.rig.split(":", 1)
        try:
            ctrl_port = int(port_str)
        except ValueError:
            log.error("Invalid port in --rig argument: %s", port_str)
            sys.exit(1)
    else:
        ctrl_host = args.rig
        ctrl_port = 9000  # Default port

    log.info("Starting SPIM Node: %s", args.node_id)
    log.info("Rig controller: %s:%d", ctrl_host, ctrl_port)
    log.info("Log port: %d, Start port: %d", args.log_port, args.start_port)

    # Call run_node_service directly
    run_node_service(
        node_id=args.node_id,
        ctrl_host=ctrl_host,
        ctrl_port=ctrl_port,
        log_port=args.log_port,
        start_port=args.start_port,
        service_cls=SpimNodeService,
    )


def main() -> None:
    """Main entry point for spim-rig CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Dispatch to appropriate handler
    if args.command == "rig":
        run_rig(args)
    elif args.command == "node":
        run_node(args)
    else:
        # Should never happen due to required=True in subparsers
        parser.print_help()
        sys.exit(1)


def node_main() -> None:
    """Entry point for spim-node command (backward compatibility alias).

    Transforms arguments to call 'spim-rig node' with the new CLI format.
    """
    # Insert 'node' subcommand into argv to use the main parser
    sys.argv.insert(1, "node")
    main()


if __name__ == "__main__":
    main()

"""The ``rigup`` command."""

import argparse
import sys
from collections.abc import Sequence

from rigup.node import serve_node


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run it. With no command, print the help."""
    parser = argparse.ArgumentParser(prog="rigup", description="Host and drive devices across machines.")
    commands = parser.add_subparsers(dest="command", metavar="<command>")
    node = commands.add_parser("node", help="run a node daemon that hosts devices for a remote rig")
    node.add_argument("node_id", help="node identifier, as named in the rig config")
    node.add_argument("--address", "-a", required=True, help="ZMQ bind address, such as tcp://0.0.0.0:5555")
    node.add_argument("--debug", action="store_true", help="enable debug logging")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    match args.command:
        case None:
            parser.print_help()
        case "node":
            serve_node(args.node_id, args.address, debug=args.debug)
        case _:
            raise AssertionError(f"Unhandled command: {args.command}")


__all__ = ["main"]

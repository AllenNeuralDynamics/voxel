"""The ``rigup`` command."""

import argparse
import sys
from collections.abc import Sequence

from rigup.node import serve_node


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run it: a product, then an action. A bare ``rigup`` or product prints its help."""
    parser = argparse.ArgumentParser(prog="rigup", description="Host and drive devices across machines.")
    parser.set_defaults(parser=parser)
    products = parser.add_subparsers(dest="product", metavar="<product>")
    node = products.add_parser(
        "node", help="host devices for a remote rig", description="host devices for a remote rig"
    )
    node.set_defaults(parser=node)
    start = node.add_subparsers(dest="action", metavar="<action>").add_parser("start", help="start a node daemon")
    start.add_argument("node_id", help="node identifier, as named in the rig config")
    start.add_argument("--address", "-a", required=True, help="ZMQ bind address, such as tcp://0.0.0.0:5555")
    start.add_argument("--debug", action="store_true", help="enable debug logging")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    match args.product, getattr(args, "action", None):
        case (None, _) | (_, None):
            args.parser.print_help()
        case "node", "start":
            serve_node(args.node_id, args.address, debug=args.debug)
        case product, action:
            raise AssertionError(f"Unhandled command: {product} {action}")


__all__ = ["main"]

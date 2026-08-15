"""Voxel-aware launcher for a remote rigup node."""

from rigup.node import serve_node

from vxl.system import load_voxel_env


def serve(node_id: str, address: str, *, debug: bool = False) -> None:
    """Load Voxel's environment, then run one node daemon."""
    load_voxel_env()
    serve_node(node_id, address, debug=debug)

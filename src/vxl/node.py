"""Voxel node entry point.

A Voxel node is a rigup node daemon that first loads this machine's ambient environment
(``~/.voxel/.env`` -- credentials, endpoint, ``VOXEL_*`` knobs) so the devices it hosts can
reach the configured object stores. rigup stays Voxel-agnostic; this wrapper owns that
Voxel-specific startup step and delegates the daemon lifecycle to :func:`rigup.node.run_node`.
"""

from rigup.node import run_node

from vxl.system import load_voxel_env


def main() -> None:
    """Load ``~/.voxel/.env``, then run the rigup node daemon CLI."""
    load_voxel_env()
    run_node()

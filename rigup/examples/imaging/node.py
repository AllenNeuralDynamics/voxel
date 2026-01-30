"""Entry point for running an ImagingRigNode on a remote host.

This allows you to run imaging-specific node services on remote machines
that connect to a central ImagingRig controller.

Usage:
    cd examples
    python -m imaging.node <node_id> [controller_addr]

Examples:
    # Connect to controller on localhost
    python -m imaging.node camera_node_1

    # Connect to remote controller
    python -m imaging.node camera_node_1 tcp://192.168.1.100:9000
"""

from rigup.cluster.node import main

from rigup import RigNode


class ImagingRigNode(RigNode):
    """Custom RigNode for imaging applications."""


if __name__ == "__main__":
    main(ImagingRigNode)

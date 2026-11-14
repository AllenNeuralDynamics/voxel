"""Run a node daemon as a child process of the orchestrator.

Configures no logging: the child shares the parent's terminal. Running ``rigup.node._runner`` with
``-m`` instead would re-import a module the package already loaded and raise a RuntimeWarning.
"""

import asyncio
import sys

from rigup.node._remote import _parse_address
from rigup.node._runner import run

if len(sys.argv) != 3:
    raise SystemExit("usage: python -m rigup.node <node_id> <address>")

asyncio.run(run(sys.argv[1], _parse_address(sys.argv[2])))

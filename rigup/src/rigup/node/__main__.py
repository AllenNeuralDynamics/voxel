"""``python -m rigup.node`` — the daemon entry point :class:`SubprocessNode` spawns.

Spawned as ``python -m rigup.node <node_id> <address>``. A subprocess node shares the parent's
terminal, so it configures no logging (the parent owns the console) and calls :func:`_run`
directly. Using ``__main__`` rather than ``python -m rigup.node._runner`` avoids re-importing a
module the package ``__init__`` already loaded, which would trigger a RuntimeWarning.
"""

import asyncio
import sys

from rigup.node._remote import _parse_address
from rigup.node._runner import run

if len(sys.argv) != 3:
    raise SystemExit("usage: python -m rigup.node <node_id> <address>")

asyncio.run(run(sys.argv[1], _parse_address(sys.argv[2])))

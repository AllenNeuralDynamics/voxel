"""Can a rigup node see that its station died from the ZMQ connection alone, with no heartbeat? A node binds a
ROUTER, as ``ZMQTransportServer`` does, and watches it with a ZMQ socket monitor. A station connects a DEALER, as
``ZMQTransportClient`` does, sends 1 message, and is killed with SIGKILL. The node writes when the connection ended.

Run: ``uv run python -m prototypes.orphans.zmq_watch``
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zmq
from zmq.utils.monitor import recv_monitor_message


class Node:
    """Binds a ROUTER at ``address`` and prints each connect and disconnect of a peer, with the time."""

    def __init__(self, address: str) -> None:
        self._address = address

    def run(self) -> None:
        router = zmq.Context.instance().socket(zmq.ROUTER)
        monitor = router.get_monitor_socket(zmq.EVENT_ACCEPTED | zmq.EVENT_DISCONNECTED)
        router.bind(self._address)
        print("bound", flush=True)
        while True:
            event = recv_monitor_message(monitor)
            name = "connected" if event["event"] == zmq.EVENT_ACCEPTED else "disconnected"
            print(f"{name} {time.time()}", flush=True)


class Station:
    """Connects a DEALER to ``address``, sends 1 message and waits to be killed."""

    def __init__(self, address: str) -> None:
        self._address = address

    def run(self) -> None:
        dealer = zmq.Context.instance().socket(zmq.DEALER)
        dealer.connect(self._address)
        dealer.send(b"claim")
        print("connected", flush=True)
        time.sleep(3600)


class Compare:
    """Runs the node and a station over TCP and over IPC, kills the station, and reports when the node noticed."""

    def run(self) -> None:
        folder = tempfile.mkdtemp()
        for address in ("tcp://127.0.0.1:57931", f"ipc://{Path(folder) / 'node'}"):
            node = self._start("node", address)
            assert node.stdout is not None
            node.stdout.readline()
            station = self._start("station", address)
            assert station.stdout is not None
            station.stdout.readline()
            assert node.stdout.readline().startswith("connected")
            killed = time.time()
            os.kill(station.pid, signal.SIGKILL)
            station.wait()
            line = node.stdout.readline().split()
            print(f"{address.split(':')[0]:4} the node saw '{line[0]}' {float(line[1]) - killed:.3f} s after the kill")
            node.kill()
            node.wait()

    @staticmethod
    def _start(role: str, address: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-m", "prototypes.orphans.zmq_watch", role, address], stdout=subprocess.PIPE, text=True
        )


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["node", address]:
            Node(address).run()
        case ["station", address]:
            Station(address).run()
        case _:
            Compare().run()

"""What outlives a hard kill of the station today. A stand-in station starts the 3 kinds of child that ``vxl station
start`` can have (the server, a rigup device node, a writer worker with its shared memory). Then it is killed with
SIGKILL, and this script lists what is left, and removes it.

Run: ``uv run python -m prototypes.orphans.today``
"""

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from multiprocessing.shared_memory import SharedMemory

import psutil
from ome_zarr_writer.dataset import ScaleLevel
from ome_zarr_writer.slot import BatchSlot
from rigup.config import DeviceConfig, NodeConfig, RigConfig
from rigup.rig import Rig
from vxlib.dtype import Dtype
from vxlib.vector import UIVec3D


class Station:
    """The stand-in station: it starts each kind of child, prints what it started as 1 JSON line, and waits."""

    async def run(self) -> None:

        port = self._free_port()
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "vxl.web.server",
            "--upstream",
            "http://127.0.0.1:9/api/stations/s",
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        )
        laser = DeviceConfig(target="vxl.devices.light.simulated.SimulatedLaser", init={"wavelength": 488})
        rig = Rig(RigConfig(nodes={"lasers": NodeConfig(devices={"laser": laser})}), "orphans")
        await rig.open()
        name = f"orphans{os.getpid()}"
        slot = BatchSlot(name, UIVec3D(z=4, y=64, x=64), ScaleLevel.L1, Dtype.UINT16)
        slot._executor.submit(os.getpid).result()  # the pool starts its worker at the first task
        shms = [shm.name for shm in slot._shms.values()]
        print(json.dumps({"station": os.getpid(), "server_port": port, "shared_memory": shms}), flush=True)
        await asyncio.Event().wait()

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            return free.getsockname()[1]


class HardKill:
    """Starts the stand-in station, kills it with SIGKILL, and reports what is left after ``settle_s``."""

    def __init__(self, settle_s: float = 3.0) -> None:
        self._settle_s = settle_s

    def run(self) -> None:
        station = subprocess.Popen(
            [sys.executable, "-m", "prototypes.orphans.today", "station"], stdout=subprocess.PIPE, text=True
        )
        started = json.loads(station.stdout.readline())
        time.sleep(1.0)  # the server child takes its port
        children = psutil.Process(station.pid).children(recursive=True)
        print("Children of the station before the kill:")
        for child in children:
            print(f"   {child.pid:>6}  {self._what(child)}")
        print(f"   server answers on its port: {self._answers(started['server_port'])}")
        print(f"   shared memory: {started['shared_memory']}")

        os.kill(station.pid, signal.SIGKILL)
        station.wait()
        time.sleep(self._settle_s)

        print(f"\n{self._settle_s:.0f} s after SIGKILL of the station:")
        left = [child for child in children if child.is_running() and child.status() != psutil.STATUS_ZOMBIE]
        for child in children:
            state = "STILL RUNNING" if child in left else "gone"
            print(f"   {child.pid:>6}  {state:13}  {self._what(child) if child in left else ''}")
        print(f"   server answers on its port: {self._answers(started['server_port'])}")
        for name in started["shared_memory"]:
            print(f"   shared memory {name}: {'STILL THERE' if self._exists(name) else 'gone'}")

        for child in left:
            with contextlib.suppress(psutil.NoSuchProcess):
                child.kill()
        for name in started["shared_memory"]:
            with contextlib.suppress(FileNotFoundError):
                shm = SharedMemory(name=name, create=False, track=False)
                shm.close()
                shm.unlink()

    @staticmethod
    def _what(process: psutil.Process) -> str:
        try:
            line = " ".join(process.cmdline())
        except psutil.Error:
            return "?"
        for mark, name in (
            ("vxl.web.server", "server"),
            ("rigup.node", "rigup device node"),
            ("resource_tracker", "multiprocessing resource tracker"),
            ("spawn_main", "writer worker (spawn)"),
        ):
            if mark in line:
                return name
        return line[:80]

    @staticmethod
    def _answers(port: int) -> bool:
        with socket.socket() as probe:
            probe.settimeout(1)
            return probe.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def _exists(name: str) -> bool:
        try:
            SharedMemory(name=name, create=False, track=False).close()
        except FileNotFoundError:
            return False
        return True


if __name__ == "__main__":
    if sys.argv[1:] == ["station"]:
        asyncio.run(Station().run())
    else:
        HardKill().run()

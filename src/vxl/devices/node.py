"""A device that reports on the node it runs in: the node's process and the machine it runs on."""

import os
import platform
import shutil
import socket
import sys

import psutil
from pydantic import TypeAdapter
from rigup.device import Device, DeviceController, DeviceHandle, fact, stream
from rigup.device.handle import Adapter, PropView

from vxl.system import ProcessEntry, System, remote_store_fingerprint

_GIB = 1024**3


class NodeMonitorController(DeviceController["NodeMonitor"], streaming={"slow": 60.0}):
    """Polls the slow streams of a node monitor once a minute; a rig file can set another interval."""


class NodeMonitor(Device, kind="node_monitor", controller=NodeMonitorController):
    """The process of a node and the machine it runs on, as Voxel uses them. A rig adds one to each node it wants
    reported. While open, it registers its process in the machine's registry under its own uid."""

    def __init__(self, uid: str) -> None:
        super().__init__(uid=uid)
        self._system = System()
        self._system.registry.join(uid)

    def dispose(self) -> None:
        self._system.registry.leave()

    @property
    @fact(desc="Process ID of the node")
    def pid(self) -> int:
        return os.getpid()

    @property
    @fact(units="s", desc="Unix time at which the node's process started")
    def process_started(self) -> float:
        return psutil.Process().create_time()

    @property
    @fact(desc="Python version of the node")
    def python(self) -> str:
        return sys.version.split()[0]

    @property
    @fact(desc="Network name of the machine")
    def hostname(self) -> str:
        return socket.gethostname()

    @property
    @fact(desc="Operating system of the machine")
    def platform(self) -> str:
        return platform.platform()

    @property
    @fact(desc="Logical CPU cores of the machine")
    def cpu_count(self) -> int:
        return os.cpu_count() or 1

    @property
    @fact(units="GiB", desc="Total RAM of the machine")
    def total_ram_gib(self) -> float:
        return round(System.total_ram_bytes() / _GIB, 2)

    @property
    @fact(desc="Fraction of the available RAM that Voxel may use on the machine")
    def max_ram_fraction(self) -> float:
        return self._system.max_ram_fraction

    @property
    @fact(desc="Object stores configured on the machine, each with a non-secret fingerprint of its connection")
    def object_stores(self) -> dict[str, str]:
        return {name: remote_store_fingerprint(remote.connection) for name, remote in self._system.remotes.items()}

    @property
    @stream("slow", units="GiB", desc="RAM that Voxel may use on the machine, rounded down to a quarter GiB")
    def ram_budget_gib(self) -> float:
        return self._system.ram_budget_bytes // (_GIB // 4) / 4

    @property
    @stream("slow", units="GiB", desc="Free space of the local store, rounded down to a whole GiB")
    def store_free_gib(self) -> int:
        root = self._system.store
        while not root.exists():
            root = root.parent
        return shutil.disk_usage(root).free // _GIB

    @property
    @stream("slow", desc="Voxel processes registered on the machine, with what each claims of the shared resources")
    def processes(self) -> list[ProcessEntry]:
        registry = self._system.registry
        registry.join(self.uid)  # restores this process after the registry file was rebuilt
        return registry.processes()


class NodeMonitorHandle(DeviceHandle[NodeMonitor]):
    """A node monitor, typed."""

    def __init__(self, adapter: Adapter[NodeMonitor]) -> None:
        super().__init__(adapter)
        self.pid: PropView[int] = self.props.view("pid", TypeAdapter(int).validate_python)
        self.hostname: PropView[str] = self.props.view("hostname", TypeAdapter(str).validate_python)
        self.cpu_count: PropView[int] = self.props.view("cpu_count", TypeAdapter(int).validate_python)
        self.total_ram_gib: PropView[float] = self.props.view("total_ram_gib", TypeAdapter(float).validate_python)
        self.ram_budget_gib: PropView[float] = self.props.view("ram_budget_gib", TypeAdapter(float).validate_python)
        self.store_free_gib: PropView[int] = self.props.view("store_free_gib", TypeAdapter(int).validate_python)
        self.processes: PropView[list[ProcessEntry]] = self.props.view(
            "processes", TypeAdapter(list[ProcessEntry]).validate_python
        )


__all__ = ["NodeMonitor", "NodeMonitorController", "NodeMonitorHandle"]

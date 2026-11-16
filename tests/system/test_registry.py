"""The registry of the Voxel processes on one machine, and the RAM budget they share through it."""

import sqlite3
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from vxl.system import System

_GIB = 1024**3
_OTHER_PROCESS = """
import sys
from vxl.system import System

system = System()
system.registry.join("other")
budget = system.ram
budget.reserve("cam_b", weight=float(sys.argv[1]))
print("ready", flush=True)
if sys.stdin.readline().strip() == "release":
    budget.release("cam_b")
    print("released", flush=True)
    sys.stdin.readline()
"""


@pytest.fixture
def system(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> System:
    """A system with its own home, 8 GiB of available RAM, and half of it as its budget."""
    monkeypatch.setenv("VOXEL_HOME", str(tmp_path))
    monkeypatch.setenv("VOXEL_MAX_RAM_FRACTION", "0.5")
    monkeypatch.setattr(System, "available_ram_bytes", staticmethod(lambda: 8 * _GIB))
    return System()


@pytest.fixture
def other(system: System) -> Generator[subprocess.Popen[str]]:
    """Another process on the machine that has joined the registry and reserved RAM for ``cam_b`` with weight 1."""
    del system  # the other process inherits its home
    process = subprocess.Popen(
        [sys.executable, "-c", _OTHER_PROCESS, "1"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "ready"
    yield process
    process.kill()
    process.wait()


def test_one_process_gets_the_whole_budget(system: System) -> None:
    assert system.ram_budget_bytes == 4 * _GIB
    assert system.ram.reserve("cam_a") == 4 * _GIB


def test_consumers_in_one_process_share_by_weight(system: System) -> None:
    budget = system.ram
    budget.reserve("cam_a", weight=1)
    budget.reserve("cam_b", weight=3)

    assert (budget.reserved("cam_a"), budget.reserved("cam_b")) == (1 * _GIB, 3 * _GIB)


def test_two_processes_share_the_budget(system: System, other: subprocess.Popen[str]) -> None:
    assert system.ram.reserve("cam_a") == 2 * _GIB
    assert system.registry.claims("ram") == {(system.registry.pid, "cam_a"): 1.0, (other.pid, "cam_b"): 1.0}


def test_a_release_in_another_process_gives_its_share_back(system: System, other: subprocess.Popen[str]) -> None:
    budget = system.ram
    budget.reserve("cam_a")
    assert other.stdin is not None
    assert other.stdout is not None

    other.stdin.write("release\n")
    other.stdin.flush()
    assert other.stdout.readline().strip() == "released"

    assert budget.reserved("cam_a") == 4 * _GIB


def test_a_process_that_dies_loses_its_claims(system: System, other: subprocess.Popen[str]) -> None:
    budget = system.ram
    assert budget.reserve("cam_a") == 2 * _GIB

    other.kill()
    other.wait()

    assert budget.reserved("cam_a") == 4 * _GIB
    assert [entry.pid for entry in system.registry.processes()] == [system.registry.pid]


def test_the_registry_lists_each_process_with_its_claims(system: System, other: subprocess.Popen[str]) -> None:
    system.registry.join("station")
    system.ram.reserve("cam_a", weight=2)

    listed = {entry.name: (entry.pid, entry.claims) for entry in system.registry.processes()}

    assert listed == {
        "station": (system.registry.pid, {"ram": {"cam_a": 2.0}}),
        "other": (other.pid, {"ram": {"cam_b": 1.0}}),
    }


def test_a_process_that_leaves_takes_its_claims_with_it(system: System) -> None:
    system.registry.claim("ram", "cam_a", 1.0)

    system.registry.leave()

    assert system.registry.claims("ram") == {}
    assert system.registry.processes() == []


def test_an_unknown_consumer_is_refused(system: System) -> None:
    with pytest.raises(KeyError, match="cam_x"):
        system.ram.reserved("cam_x")
    with pytest.raises(ValueError, match="weight"):
        system.ram.reserve("cam_a", weight=0)


def test_a_file_of_another_version_is_rebuilt_and_live_claims_come_back(system: System) -> None:
    budget = system.ram
    budget.reserve("cam_a")
    path = next((system.dir / "run").glob("machine-*.db"))
    old = sqlite3.connect(path)
    old.execute("DROP TABLE claims")
    old.execute("PRAGMA user_version = 0")
    old.commit()
    old.close()

    assert budget.reserved("cam_a") == 4 * _GIB
    assert system.registry.claims("ram") == {(system.registry.pid, "cam_a"): 1.0}


def test_a_wrong_value_is_refused_by_the_file(system: System) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        system.registry.claim("ram", "cam_a", 0)

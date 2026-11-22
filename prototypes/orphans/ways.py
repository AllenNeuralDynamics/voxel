"""4 ways for a child to end when its parent dies, compared on this computer: end of file on a stdin pipe, polling
the parent's id, the OS's own notice (kqueue on macOS and BSD), and, for a multiprocessing child, the parent's
sentinel (``multiprocessing.parent_process().sentinel``). A parent starts 1 child for each way, and 1 more child
after them that holds nothing (to check that a sibling does not keep the pipe open). Then the parent is killed with
SIGKILL, and each child writes when it noticed.

Run: ``uv run python -m prototypes.orphans.ways``
"""

import contextlib
import json
import multiprocessing as mp
import multiprocessing.connection
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_POLL_S = 1.0
"""How often a child polls its parent's id, as Jupyter's kernel does."""

_WAYS = ("stdin", "ppid", "kqueue")


class Child:
    """1 child: it waits for its parent to die in 1 way, then writes the time to ``out``."""

    def __init__(self, way: str, out: Path) -> None:
        self._way = way
        self._out = out

    def run(self) -> None:
        if self._way == "stdin":
            sys.stdin.buffer.read()  # returns at end of file: every write end of the pipe is closed
        elif self._way == "ppid":
            first = os.getppid()
            while os.getppid() == first:  # compare with the first parent, not with 1 (Jupyter's PR #1271)
                time.sleep(_POLL_S)
        elif self._way == "kqueue":
            parent = os.getppid()
            queue = select.kqueue()
            watch = select.kevent(parent, select.KQ_FILTER_PROC, select.KQ_EV_ADD, select.KQ_NOTE_EXIT)
            queue.control([watch], 0)
            if os.getppid() == parent:  # the parent may have died before the watch was set
                queue.control(None, 1, None)
        self._out.write_text(json.dumps({"noticed": time.time()}))

    @staticmethod
    def watch_sentinel(out: str) -> None:
        """A multiprocessing child (spawn): wait on the parent's sentinel, which is ready when the parent ends."""
        parent = mp.parent_process()
        assert parent is not None
        mp.connection.wait([parent.sentinel])
        Path(out).write_text(json.dumps({"noticed": time.time()}))


class Parent:
    """Starts 1 child for each way and 1 sibling, then says it is ready and waits to be killed."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def run(self) -> None:
        children = [
            subprocess.Popen(
                [sys.executable, "-m", "prototypes.orphans.ways", "child", way, str(self._folder / way)],
                stdin=subprocess.PIPE if way == "stdin" else subprocess.DEVNULL,
            )
            for way in _WAYS
        ]
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])  # inherits no pipe
        worker = mp.get_context("spawn").Process(target=Child.watch_sentinel, args=(str(self._folder / "sentinel"),))
        worker.start()
        time.sleep(1.5)  # each child has set its watch
        print(json.dumps([child.pid for child in [*children, sibling]] + [worker.pid]), flush=True)
        time.sleep(3600)


class Compare:
    """Kills the parent with SIGKILL and reports how long each child took to notice."""

    def run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            parent = subprocess.Popen(
                [sys.executable, "-m", "prototypes.orphans.ways", "parent", folder], stdout=subprocess.PIPE, text=True
            )
            pids = json.loads(parent.stdout.readline())
            killed = time.time()
            os.kill(parent.pid, signal.SIGKILL)
            parent.wait()
            time.sleep(_POLL_S * 3)
            print("After SIGKILL of the parent:")
            for way in (*_WAYS, "sentinel"):
                out = Path(folder) / way
                shown = f"{json.loads(out.read_text())['noticed'] - killed:.3f} s" if out.exists() else "NOT NOTICED"
                print(f"   {way:8} {shown}")
            for pid in pids:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
            self._empty_stdin(Path(folder))

    @staticmethod
    def _empty_stdin(folder: Path) -> None:
        """A service manager often gives a program an empty stdin (``/dev/null``): the stdin way then ends it at once,
        although its parent lives."""
        out = folder / "devnull"
        started = time.time()
        child = subprocess.run(
            [sys.executable, "-m", "prototypes.orphans.ways", "child", "stdin", str(out)],
            stdin=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        noticed = json.loads(out.read_text())["noticed"] - started
        shown = f"ended after {noticed:.3f} s (code {child.returncode})"
        print(f"   stdin way with an empty stdin and a living parent: {shown}")


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["child", way, out]:
            Child(way, Path(out)).run()
        case ["parent", folder]:
            Parent(Path(folder)).run()
        case _:
            Compare().run()

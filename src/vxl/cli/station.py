"""The station's commands: creating its ``station.yaml``, checking it and its instrument folders, and starting the
station service with its server."""

import asyncio
import contextlib
import errno
import inspect
import logging
import signal
import socket
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self, TextIO
from uuid import UUID

from pydantic import ValidationError
from vxlib.issues import Problem

from vxl._utils.logging import configure_logging
from vxl.instrument.folder import InstrumentFolder
from vxl.station.config import StationConfig
from vxl.station.errors import StationNotConfiguredError
from vxl.system import load_voxel_env

from .report import CheckedTarget, write_report

if TYPE_CHECKING:
    from vxl.web.station.service import StationService


class _Initializable(Protocol):
    """A station config that can write its own ``station.yaml``."""

    id: UUID
    name: str

    @classmethod
    def initialize(cls, name: str, *, station_id: UUID | None = None) -> Self: ...

    @classmethod
    def config_path(cls) -> Path: ...


def initialize(name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO) -> int:
    """Create the station's ``station.yaml`` and report a shell-friendly status."""
    return initialize_with(StationConfig, name, station_id=station_id, output=output, errors=errors)


def initialize_with(
    config: type[_Initializable], name: str, *, station_id: UUID | None, output: TextIO, errors: TextIO
) -> int:
    """Create the ``station.yaml`` of ``config`` and report a shell-friendly status."""
    load_voxel_env()
    try:
        station = config.initialize(name, station_id=station_id)
    except (FileExistsError, ValidationError) as exc:
        errors.write(f"{exc}\n")
        return 2
    output.write(f"Initialized control station '{station.name}' ({station.id}) at {station.config_path()}\n")
    return 0


def run_check(paths: Sequence[Path], *, as_json: bool, output: TextIO) -> int:
    """Check instrument folders, or with no ``paths``, ``station.yaml`` and every instrument folder of the station.
    Give back 0 when all is well, 1 when something is wrong, and 2 when a path does not exist."""
    load_voxel_env()
    targets: list[CheckedTarget] = []
    if not paths:
        targets.append(_check_station())
        root = StationConfig.station_dir() / "instruments"
        paths = sorted(root.glob("*.voxel")) if root.is_dir() else []
    missing = False
    for path in paths:
        if not path.is_dir():
            missing = True
            problem = Problem(code="target.not_found", msg=f"No instrument folder at {path}")
            targets.append(CheckedTarget(path, ok=False, findings=(problem,)))
            continue
        folder = InstrumentFolder.read(path)
        targets.append(CheckedTarget(path, ok=folder.ok, findings=tuple(folder.problems)))
    write_report(targets, as_json=as_json, output=output, nothing="Nothing to check.")
    if missing:
        return 2
    return 0 if all(target.ok for target in targets) else 1


def _check_station() -> CheckedTarget:
    """Whether ``station.yaml`` loads."""
    path = StationConfig.config_path()
    try:
        StationConfig.load()
    except (StationNotConfiguredError, ValidationError, ValueError) as error:
        return CheckedTarget(path, ok=False, findings=(Problem(code="station.load", msg=str(error)),))
    return CheckedTarget(path, ok=True)


class StationRun:
    """1 run of ``vxl station start``: the station service in this process, and its server as a child process that is
    started again when it stops, after a wait that doubles up to :attr:`LONGEST_WAIT_S` while it stops early. With
    ``headless``, no server starts: the station runs with no windows."""

    LONGEST_WAIT_S = 30.0

    def __init__(
        self, service: "type[StationService]", config: StationConfig, *, headless: bool, output: TextIO
    ) -> None:
        self._service = service
        self._config = config
        self._headless = headless
        self._output = output

    async def run(self) -> None:
        """Run until the task is cancelled or the program is told to end, then stop the server and close the
        station."""
        task = asyncio.current_task()
        if task is not None and sys.platform != "win32":  # Ctrl+C cancels the task already
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, task.cancel)
            loop.add_signal_handler(signal.SIGHUP, task.cancel)
        async with self._service(self._config) as service:
            self._say(f"Station '{self._config.name}' is running.")
            if self._headless:
                await asyncio.Event().wait()
            await self._keep_server(self._server_command(service))

    def _server_command(self, service: "StationService") -> list[str]:
        """The server program and its flags, which are the same for every server program. The web app is the folder
        that ``server.web`` names, or else the built app in the package of the service, when it is there."""
        settings = self._config.server
        program = [settings.command] if settings.command else [sys.executable, "-m", "vxl.web.server"]
        flags = ["--upstream", service.url, "--port", str(settings.port)]
        flags += ["--records", str(service.station.records.path), "--data", str(self._config.store)]
        web = settings.web or self._built_app()
        if web is not None:
            flags += ["--web", str(web)]
        return program + flags

    def _built_app(self) -> Path | None:
        """The built web app of the service: the ``static`` folder next to its module. ``None`` when it is not
        built."""
        folder = Path(inspect.getfile(self._service)).parent / "static"
        return folder if (folder / "index.html").is_file() else None

    async def _keep_server(self, command: Sequence[str]) -> None:
        port = self._config.server.port
        wait = 1.0
        while True:
            if self._taken(port):
                self._say(f"Port {port} is in use: the server cannot start. Trying again in {wait:.0f} s.")
            else:
                started = time.monotonic()
                process = await asyncio.create_subprocess_exec(*command)
                try:
                    if await self._answers(process, port):
                        self._say(f"Open http://{self._config.hostname()}:{port}")
                    code = await process.wait()
                finally:
                    if process.returncode is None:
                        with contextlib.suppress(ProcessLookupError):
                            process.terminate()
                        await process.wait()
                if time.monotonic() - started > self.LONGEST_WAIT_S:
                    wait = 1.0
                self._say(f"The server stopped (exit code {code}). Starting it again in {wait:.0f} s.")
            await asyncio.sleep(wait)
            wait = min(wait * 2, self.LONGEST_WAIT_S)

    @staticmethod
    def _taken(port: int) -> bool:
        """Whether another program listens on ``port``."""
        try:
            socket.create_server(("", port)).close()
        except OSError:
            return True
        return False

    @staticmethod
    async def _answers(process: asyncio.subprocess.Process, port: int) -> bool:
        """Wait until the server takes connections on ``port``. Give back False when it stops before that."""
        while process.returncode is None:
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", port)
            except OSError:
                await asyncio.sleep(0.1)
                continue
            writer.close()
            return True
        return False

    def _say(self, text: str) -> None:
        """Write a line now, also when the output is a pipe or a file."""
        self._output.write(f"{text}\n")
        self._output.flush()


def start(service: "type[StationService]", *, headless: bool, output: TextIO, errors: TextIO) -> int:
    """Start the station service and its server, and run until interrupted. Give back 2 when there is no usable
    ``station.yaml``, and 3 when the port of the station service is in use."""
    load_voxel_env()
    try:
        config = StationConfig.load()
    except (StationNotConfiguredError, ValidationError, ValueError) as error:
        errors.write(f"{error}\n")
        return 2
    configure_logging(level=logging.INFO)
    try:
        asyncio.run(StationRun(service, config, headless=headless, output=output).run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        errors.write(f"The port of the station service is in use: is this station running already? ({error})\n")
        return 3
    return 0


__all__ = ["StationRun", "initialize", "initialize_with", "run_check", "start"]

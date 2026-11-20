"""Shell words plus the described properties and operations of the active device."""

import cmd
import logging
import shlex
import time
from collections.abc import Iterable, Sequence
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.text import Text
from rigup.device import DeviceController, PropModel
from rigup.interface import OperationInfo, PropInfo
from ruamel.yaml import YAML

from .session import Session, load_configs, stop

_WATCH_INTERVAL_S = 0.5


class Output:
    """Print to the terminal and, when given, append a plain-text transcript."""

    def __init__(self, console: Console, transcript: TextIO | None = None) -> None:
        self.console = console
        self._transcript = Console(file=transcript, width=120) if transcript else None

    def print(self, *objects: Any, style: str | None = None) -> None:
        for console in (self.console, self._transcript):
            if console is not None:
                console.print(*objects, style=style, markup=False)

    def record_input(self, line: str) -> None:
        if self._transcript:
            self._transcript.print(f"{datetime.now():%H:%M:%S} {line}", markup=False, highlight=False)


class DeviceShell(cmd.Cmd):
    prompt = "> "

    def __init__(self, session: Session, output: Output) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._id: str | None = None
        self._controller: DeviceController[Any] | None = None
        self._properties: dict[str, PropInfo] = {}
        self._commands: dict[str, OperationInfo] = {}

    def open(self, device_ids: Iterable[str]) -> None:
        """Open devices before the loop starts; the first that opens becomes active."""
        for device_id in device_ids:
            if self._open(device_id) and self._id is None:
                self._activate(device_id)

    def run(self) -> None:
        while True:
            try:
                self.cmdloop()
                return
            except KeyboardInterrupt:
                self._output.print()

    def precmd(self, line: str) -> str:
        """Record the line; ``cmd`` gives Ctrl+D as the line ``EOF``, which quits."""
        if line == "EOF":
            self._output.print()
            return "quit"
        self._output.record_input(self.prompt + line)
        return line

    def emptyline(self) -> bool:
        return False

    def onecmd(self, line: str) -> bool:
        try:
            return super().onecmd(line)
        except KeyboardInterrupt:
            self._output.print("Interrupted", style="yellow")
            if self._id is not None:
                self._stop(self._id)
        except Exception as error:
            self._report(error)
        return False

    def default(self, line: str) -> None:
        controller = self._active()
        name, *tokens = shlex.split(line)
        if name in self._properties:
            self._property(controller, name, tokens)
        elif name in self._commands:
            self._command(name, tokens)
        else:
            raise ValueError(f"{self._id} has no property or operation {name!r}; see 'info'")

    def completenames(self, text: str, *ignored: Any) -> list[str]:
        members = [name for name in (*self._properties, *self._commands) if name.startswith(text)]
        return super().completenames(text, *ignored) + members

    def complete_use(self, text: str, *_ignored: Any) -> list[str]:
        return [dev_id for dev_id in self._session.configs if dev_id.startswith(text)]

    def complete_watch(self, text: str, *_ignored: Any) -> list[str]:
        return [name for name in self._properties if name.startswith(text)]

    def do_use(self, arg: str) -> None:
        """use [<device>]: list the devices, or open one if needed and make it active."""
        if not arg:
            self._list()
        elif self._open(arg):
            self._activate(arg)

    def do_info(self, _arg: str) -> None:
        """info: show the active device's properties and operations."""
        controller = self._active()
        properties = Table("Property", "Value", "Units", "Access", "Limits", "Step")
        results = self._session.run(controller.get_props(*self._properties))
        for name, info in self._properties.items():
            if (error := results[name].error) is not None:
                properties.add_row(Text(name), Text(error, style="red"))
                continue
            model = results[name].unwrap()
            cells = (name, model.value, info.units, info.access, _limits(model), model.step)
            properties.add_row(*(Text(_text(cell)) for cell in cells))
        operations = Table("Operation", "Parameters")
        for name, operation in self._commands.items():
            operations.add_row(Text(name), Text(", ".join(_params(operation))))
        self._output.print(properties, operations)

    def do_watch(self, arg: str) -> None:
        """watch <property> [<property> ...]: read every 0.5 s until Ctrl+C."""
        controller = self._active()
        names = arg.split()
        if not names:
            raise ValueError("watch needs at least one property")
        if unknown := [name for name in names if name not in self._properties]:
            raise ValueError(f"{self._id} has no property {', '.join(unknown)}")
        try:
            while True:
                stamp = f"{datetime.now():%H:%M:%S}"
                for name in names:
                    self._output.print(f"{stamp}  {name}  {self._format(controller, name)}")
                time.sleep(_WATCH_INTERVAL_S)
        except KeyboardInterrupt:
            self._output.print()

    def do_stop(self, _arg: str) -> None:
        """stop: run the failsafe operations of every open device."""
        for device_id in reversed(self._session.controllers):
            self._stop(device_id)

    def do_quit(self, _arg: str) -> bool:
        """quit: close every open device and exit. Ctrl+D does the same."""
        return True

    def _open(self, device_id: str) -> bool:
        opened, errors = self._session.open(device_id)
        if opened:
            self._output.print(f"Opened {', '.join(opened)}")
        for name, error in errors.items():
            self._output.print(f"Could not open {name}: {error.msg}", style="red")
        return device_id in self._session.devices

    def _activate(self, device_id: str) -> None:
        self._id = device_id
        self._controller = self._session.controllers[device_id]
        self._properties = dict(self._controller.interface.props)
        self._commands = dict(self._controller.interface.operations)
        self.prompt = f"{device_id}> "

    def _active(self) -> DeviceController[Any]:
        if self._controller is None:
            raise ValueError("No active device; use 'use <device>'")
        return self._controller

    def _list(self) -> None:
        table = Table("Device", "Class", "Open")
        for device_id, config in self._session.configs.items():
            is_open = "yes" if device_id in self._session.devices else "no"
            style = "bold" if device_id == self._id else None
            table.add_row(device_id, config.target.rsplit(".", 1)[-1], is_open, style=style)
        self._output.print(table)

    def _property(self, controller: DeviceController[Any], name: str, tokens: list[str]) -> None:
        if tokens:
            if self._properties[name].access == "ro":
                raise ValueError(f"{name} is read-only")
            if len(tokens) != 1:
                raise ValueError(f"{name} takes one value")
            if error := self._session.run(controller.set_props(**{name: _value(tokens[0])}))[name].error:
                raise ValueError(error)
        self._output.print(self._format(controller, name))

    def _command(self, name: str, tokens: list[str]) -> None:
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        for token in tokens:
            key, separator, value = token.partition("=")
            if separator and key.isidentifier():
                kwargs[key] = _value(value)
            else:
                args.append(_value(token))
        if unknown := kwargs.keys() - self._commands[name].params.get("properties", {}).keys():
            raise ValueError(f"{name} has no parameter {', '.join(sorted(unknown))}")
        result = self._session.run(self._active().execute(name, *args, **kwargs)).unwrap()
        if result is not None:
            self._output.print(result)

    def _format(self, controller: DeviceController[Any], name: str) -> str:
        value = self._session.run(controller.get_props(name))[name].unwrap().value
        units = self._properties[name].units
        return f"{value} {units}" if value is not None and units else str(value)

    def _stop(self, device_id: str) -> None:
        try:
            if self._session.run(stop(self._session.controllers[device_id])):
                self._output.print(f"Stopped {device_id}")
        except Exception as error:
            self._report(error)

    def _report(self, error: Exception) -> None:
        for item in error.exceptions if isinstance(error, ExceptionGroup) else (error,):
            self._output.print(f"{type(item).__name__}: {item}", style="red")


def _limits(model: PropModel) -> str:
    if model.options is not None:
        return ", ".join(map(str, model.options))
    if model.minimum is None and model.maximum is None:
        return ""
    return f"{_text(model.minimum)} to {_text(model.maximum)}"


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _params(operation: OperationInfo) -> list[str]:
    required = set(operation.params.get("required", []))
    params: list[str] = []
    for name, schema in operation.params.get("properties", {}).items():
        dtype = " | ".join(str(option.get("type", "?")) for option in schema.get("anyOf", [schema]))
        params.append(f"{name}: {dtype}" if name in required else f"{name}: {dtype} = {schema.get('default')}")
    return params


def run(config: Path, devices: Sequence[str] = (), *, log: Path | None = None) -> int:
    """Open the shell on the devices of ``config``, with ``devices`` open at start, and return the exit code."""
    console = Console()
    with ExitStack() as stack:
        transcript = stack.enter_context(log.open("a", encoding="utf-8")) if log else None
        output = Output(console, transcript)
        _configure_logging(console, transcript)
        try:
            session = Session(load_configs(config))
        except (OSError, ValueError) as error:
            output.print(str(error), style="red")
            return 1
        if unknown := [dev_id for dev_id in devices if dev_id not in session.configs]:
            output.print(f"Unknown devices: {', '.join(unknown)}", style="red")
            return 1

        stack.callback(_close, session, output)
        shell = DeviceShell(session, output)
        shell.open(devices)
        shell.run()
    return 0


def _configure_logging(console: Console, transcript: TextIO | None) -> None:
    terminal = RichHandler(console=console, show_time=False, show_path=False)
    terminal.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    handlers: list[logging.Handler] = [terminal]
    if transcript:
        file = logging.StreamHandler(transcript)
        file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
        handlers.append(file)
    logging.basicConfig(level=logging.WARNING, handlers=handlers)


def _close(session: Session, output: Output) -> None:
    for device_id, error in session.close().items():
        output.print(f"Could not close {device_id}: {error}", style="red")


def _value(text: str) -> Any:
    """A value typed in the shell, read as YAML: ``1.5``, ``true``, ``[1, 2]`` or a plain word."""
    return YAML(typ="safe", pure=True).load(text)

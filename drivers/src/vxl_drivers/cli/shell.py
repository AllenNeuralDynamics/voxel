"""Shell words plus the described properties and commands of the active device."""

import cmd
import shlex
import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any, TextIO

import yaml
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rigup.device import DeviceController
from rigup.device.interface import CommandInfo, PropInfo
from rigup.device.results import PropModel

from vxl_drivers.cli.devices import Session, stop

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


class DriverShell(cmd.Cmd):
    prompt = "> "

    def __init__(self, session: Session, output: Output) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._uid: str | None = None
        self._controller: DeviceController[Any] | None = None
        self._properties: dict[str, PropInfo] = {}
        self._commands: dict[str, CommandInfo] = {}

    def open(self, uids: Iterable[str]) -> None:
        """Open devices before the loop starts; the first that opens becomes active."""
        for uid in uids:
            if self._open(uid) and self._uid is None:
                self._activate(uid)

    def run(self) -> None:
        while True:
            try:
                self.cmdloop()
                return
            except KeyboardInterrupt:
                self._output.print()

    def precmd(self, line: str) -> str:
        self._output.record_input(self.prompt + line)
        return line

    def emptyline(self) -> bool:
        return False

    def onecmd(self, line: str) -> bool:
        try:
            return super().onecmd(line)
        except KeyboardInterrupt:
            self._output.print("Interrupted", style="yellow")
            if self._uid is not None:
                self._stop(self._uid)
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
            raise ValueError(f"{self._uid} has no property or command {name!r}; see 'info'")

    def completenames(self, text: str, *ignored: Any) -> list[str]:
        members = [name for name in (*self._properties, *self._commands) if name.startswith(text)]
        return super().completenames(text, *ignored) + members

    def complete_use(self, text: str, *_ignored: Any) -> list[str]:
        return [uid for uid in self._session.configs if uid.startswith(text)]

    def complete_watch(self, text: str, *_ignored: Any) -> list[str]:
        return [name for name in self._properties if name.startswith(text)]

    def do_use(self, arg: str) -> None:
        """use [<device>]: list the devices, or open one if needed and make it active."""
        if not arg:
            self._list()
        elif self._open(arg):
            self._activate(arg)

    def do_info(self, _arg: str) -> None:
        """info: show the active device's properties and commands."""
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
        commands = Table("Command", "Parameters")
        for name, command in self._commands.items():
            commands.add_row(Text(name), Text(", ".join(_params(command))))
        self._output.print(properties, commands)

    def do_watch(self, arg: str) -> None:
        """watch <property> [<property> ...]: read every 0.5 s until Ctrl+C."""
        controller = self._active()
        names = arg.split()
        if not names:
            raise ValueError("watch needs at least one property")
        if unknown := [name for name in names if name not in self._properties]:
            raise ValueError(f"{self._uid} has no property {', '.join(unknown)}")
        try:
            while True:
                stamp = f"{datetime.now():%H:%M:%S}"
                for name in names:
                    self._output.print(f"{stamp}  {name}  {self._format(controller, name)}")
                time.sleep(_WATCH_INTERVAL_S)
        except KeyboardInterrupt:
            self._output.print()

    def do_stop(self, _arg: str) -> None:
        """stop: run the failsafe commands of every open device."""
        for uid in reversed(self._session.controllers):
            self._stop(uid)

    def do_quit(self, _arg: str) -> bool:
        """quit: close every open device and exit."""
        return True

    def do_EOF(self, _arg: str) -> bool:  # noqa: N802 - cmd dispatches Ctrl+D here
        """Ctrl+D: same as quit."""
        self._output.print()
        return True

    def _open(self, uid: str) -> bool:
        opened, errors = self._session.open(uid)
        if opened:
            self._output.print(f"Opened {', '.join(opened)}")
        for name, error in errors.items():
            self._output.print(f"Could not open {name}: {error.msg}", style="red")
        return uid in self._session.devices

    def _activate(self, uid: str) -> None:
        self._uid = uid
        self._controller = self._session.controllers[uid]
        self._properties = dict(self._controller.interface.props)
        self._commands = dict(self._controller.interface.commands)
        self.prompt = f"{uid}> "

    def _active(self) -> DeviceController[Any]:
        if self._controller is None:
            raise ValueError("No active device; use 'use <device>'")
        return self._controller

    def _list(self) -> None:
        table = Table("Device", "Class", "Open")
        for uid, config in self._session.configs.items():
            is_open = "yes" if uid in self._session.devices else "no"
            style = "bold" if uid == self._uid else None
            table.add_row(uid, config.target.rsplit(".", 1)[-1], is_open, style=style)
        self._output.print(table)

    def _property(self, controller: DeviceController[Any], name: str, tokens: list[str]) -> None:
        if tokens:
            if self._properties[name].access == "ro":
                raise ValueError(f"{name} is read-only")
            if len(tokens) != 1:
                raise ValueError(f"{name} takes one value")
            if error := self._session.run(controller.set_props(**{name: yaml.safe_load(tokens[0])}))[name].error:
                raise ValueError(error)
        self._output.print(self._format(controller, name))

    def _command(self, name: str, tokens: list[str]) -> None:
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        for token in tokens:
            key, separator, value = token.partition("=")
            if separator and key.isidentifier():
                kwargs[key] = yaml.safe_load(value)
            else:
                args.append(yaml.safe_load(token))
        if unknown := kwargs.keys() - self._commands[name].params.get("properties", {}).keys():
            raise ValueError(f"{name} has no parameter {', '.join(sorted(unknown))}")
        result = self._session.run(self._active().execute_command(name, *args, **kwargs)).unwrap()
        if result is not None:
            self._output.print(result)

    def _format(self, controller: DeviceController[Any], name: str) -> str:
        value = self._session.run(controller.get_props(name))[name].unwrap().value
        units = self._properties[name].units
        return f"{value} {units}" if value is not None and units else str(value)

    def _stop(self, uid: str) -> None:
        try:
            if self._session.run(stop(self._session.controllers[uid])):
                self._output.print(f"Stopped {uid}")
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


def _params(command: CommandInfo) -> list[str]:
    required = set(command.params.get("required", []))
    params: list[str] = []
    for name, schema in command.params.get("properties", {}).items():
        dtype = " | ".join(str(option.get("type", "?")) for option in schema.get("anyOf", [schema]))
        params.append(f"{name}: {dtype}" if name in required else f"{name}: {dtype} = {schema.get('default')}")
    return params

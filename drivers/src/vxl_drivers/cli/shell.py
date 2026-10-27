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
from rigup.device.schema import Command, ParamInfo, PropertyInfo, collect_commands, collect_properties

from rigup import Device, PropertyModel
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
        self._device: Device | None = None
        self._properties: dict[str, PropertyInfo] = {}
        self._commands: dict[str, Command] = {}

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
        device = self._active()
        name, *tokens = shlex.split(line)
        if name in self._properties:
            self._property(device, name, tokens)
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
        device = self._active()
        properties = Table("Property", "Value", "Units", "Access", "Limits", "Step")
        for name, info in self._properties.items():
            try:
                model = PropertyModel.from_value(getattr(device, name))
            except Exception as error:
                properties.add_row(Text(name), Text(f"{type(error).__name__}: {error}", style="red"))
                continue
            cells = (name, model.value, info.units, info.access, _limits(model), model.step)
            properties.add_row(*(Text(_text(cell)) for cell in cells))
        commands = Table("Command", "Parameters")
        for name, command in self._commands.items():
            commands.add_row(Text(name), Text(", ".join(_param(*item) for item in command.info.params.items())))
        self._output.print(properties, commands)

    def do_watch(self, arg: str) -> None:
        """watch <property> [<property> ...]: read every 0.5 s until Ctrl+C."""
        device = self._active()
        names = arg.split()
        if not names:
            raise ValueError("watch needs at least one property")
        if unknown := [name for name in names if name not in self._properties]:
            raise ValueError(f"{self._uid} has no property {', '.join(unknown)}")
        try:
            while True:
                stamp = f"{datetime.now():%H:%M:%S}"
                for name in names:
                    self._output.print(f"{stamp}  {name}  {self._format(device, name)}")
                time.sleep(_WATCH_INTERVAL_S)
        except KeyboardInterrupt:
            self._output.print()

    def do_stop(self, _arg: str) -> None:
        """stop: turn lasers off, halt axes, and stop cameras on every open device."""
        for uid in reversed(self._session.devices):
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
            self._output.print(f"Could not open {name}: {error.message}", style="red")
        return uid in self._session.devices

    def _activate(self, uid: str) -> None:
        self._uid = uid
        self._device = self._session.devices[uid]
        self._properties = collect_properties(self._device)
        self._commands = collect_commands(self._device)
        self.prompt = f"{uid}> "

    def _active(self) -> Device:
        if self._device is None:
            raise ValueError("No active device; use 'use <device>'")
        return self._device

    def _list(self) -> None:
        table = Table("Device", "Class", "Open")
        for uid, config in self._session.configs.items():
            is_open = "yes" if uid in self._session.devices else "no"
            style = "bold" if uid == self._uid else None
            table.add_row(uid, config.target.rsplit(".", 1)[-1], is_open, style=style)
        self._output.print(table)

    def _property(self, device: Device, name: str, tokens: list[str]) -> None:
        if tokens:
            if self._properties[name].access == "ro":
                raise ValueError(f"{name} is read-only")
            if len(tokens) != 1:
                raise ValueError(f"{name} takes one value")
            setattr(device, name, yaml.safe_load(tokens[0]))
        self._output.print(self._format(device, name))

    def _command(self, name: str, tokens: list[str]) -> None:
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        for token in tokens:
            key, separator, value = token.partition("=")
            if separator and key.isidentifier():
                kwargs[key] = yaml.safe_load(value)
            else:
                args.append(yaml.safe_load(token))
        command = self._commands[name]
        if unknown := kwargs.keys() - command.info.params.keys():
            raise ValueError(f"{name} has no parameter {', '.join(sorted(unknown))}")
        result = command(*args, **kwargs)
        if result is not None:
            self._output.print(result)

    def _format(self, device: Device, name: str) -> str:
        value = PropertyModel.from_value(getattr(device, name)).value
        units = self._properties[name].units
        return f"{value} {units}" if value is not None and units else str(value)

    def _stop(self, uid: str) -> None:
        try:
            if stop(self._session.devices[uid]):
                self._output.print(f"Stopped {uid}")
        except Exception as error:
            self._report(error)

    def _report(self, error: Exception) -> None:
        for item in error.exceptions if isinstance(error, ExceptionGroup) else (error,):
            self._output.print(f"{type(item).__name__}: {item}", style="red")


def _limits(model: PropertyModel) -> str:
    if model.options is not None:
        return ", ".join(map(str, model.options))
    if model.minimum is None and model.maximum is None:
        return ""
    return f"{_text(model.minimum)} to {_text(model.maximum)}"


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _param(name: str, info: ParamInfo) -> str:
    dtype = " | ".join(part.rsplit(".", 1)[-1] for part in info.types)
    return f"{name}: {dtype}" if info.required else f"{name}: {dtype} = {info.default}"

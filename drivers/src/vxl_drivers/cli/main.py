"""Open devices from a rig or instrument file and check them in an interactive shell."""

import argparse
import logging
from contextlib import ExitStack
from pathlib import Path
from typing import TextIO

import yaml
from rich.console import Console
from rich.logging import RichHandler

from vxl_drivers.cli.devices import Session, load_configs
from vxl_drivers.cli.shell import DriverShell, Output


def main() -> None:
    parser = argparse.ArgumentParser(prog="vxl-drivers", description=__doc__)
    parser.add_argument("config", type=Path, help="YAML with devices, such as an instrument file")
    parser.add_argument("devices", nargs="*", help="devices to open at start; the first becomes active")
    parser.add_argument("--log", type=Path, help="append a transcript to this file")
    args = parser.parse_args()

    console = Console()
    with ExitStack() as stack:
        transcript = stack.enter_context(args.log.open("a", encoding="utf-8")) if args.log else None
        output = Output(console, transcript)
        _configure_logging(console, transcript)
        try:
            session = Session(load_configs(args.config))
        except (OSError, ValueError, yaml.YAMLError) as error:
            output.print(str(error), style="red")
            raise SystemExit(1) from None
        if unknown := [uid for uid in args.devices if uid not in session.configs]:
            output.print(f"Unknown devices: {', '.join(unknown)}", style="red")
            raise SystemExit(1)

        stack.callback(_close, session, output)
        shell = DriverShell(session, output)
        shell.open(args.devices)
        shell.run()


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
    for uid, error in session.close().items():
        output.print(f"Could not close {uid}: {error}", style="red")

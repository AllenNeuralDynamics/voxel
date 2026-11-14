"""Decorators that expose device properties and commands; a missing description falls back to the docstring."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

type Units = str | Callable[[Any], str]
"""Units as text, or a function of the device read once when its interface is built."""

type StreamTier = Literal["fast", "slow"]
"""How often a streamed property is sent. The controller sets the seconds behind each tier."""

type Intent = Literal["query", "action", "failsafe"]
"""What a command is for."""

_MARK = "__rigup_mark"


@dataclass(frozen=True)
class PropMark:
    label: str | None
    desc: str | None
    units: Units | None
    stream: StreamTier | None


@dataclass(frozen=True)
class CommandMark:
    intent: Intent
    label: str | None
    desc: str | None


def prop[F: Callable[..., Any]](
    *, label: str | None = None, desc: str | None = None, units: Units | None = None, stream: StreamTier | None = None
) -> Callable[[F], F]:
    """Expose a property. Apply it below ``@property``, ``@number``, ``@integer`` or ``@choice``."""

    def decorator(getter: F) -> F:
        if isinstance(getter, property):
            made = type(getter).__name__
            raise TypeError(
                f"@prop got a {made}, not a function: put @prop under @number, @integer, @choice or @property"
            )
        getter.__dict__[_MARK] = PropMark(label, desc, units, stream)
        return getter

    return decorator


def _command[F: Callable[..., Any]](intent: Intent, label: str | None, desc: str | None) -> Callable[[F], F]:
    def decorator(method: F) -> F:
        method.__dict__[_MARK] = CommandMark(intent, label, desc)
        return method

    return decorator


def query[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a command that only looks: it can run at any time."""
    return _command("query", label, desc)


def action[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a command that changes the hardware: it waits its turn behind a running activity."""
    return _command("action", label, desc)


def failsafe[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a command that puts the device in a safe state: it can always run and takes no required arguments.

    The system calls it on "stop all", on a failure and on close."""

    def decorator(method: F) -> F:
        needed = [
            name
            for name, parameter in inspect.signature(method).parameters.items()
            if name != "self" and parameter.default is inspect.Parameter.empty
        ]
        if needed:
            raise TypeError(
                f"failsafe '{method.__name__}' needs {needed}: a failsafe must be callable with no arguments"
            )
        return _command("failsafe", label, desc)(method)

    return decorator


def mark_of(function: object) -> PropMark | CommandMark | None:
    found = getattr(function, "__dict__", {}).get(_MARK)
    return found if isinstance(found, PropMark | CommandMark) else None


__all__ = [
    "CommandMark",
    "Intent",
    "PropMark",
    "StreamTier",
    "Units",
    "action",
    "failsafe",
    "mark_of",
    "prop",
    "query",
]

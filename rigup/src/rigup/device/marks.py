"""Decorators that declare a device's public interface.

A property is exposed by marking its getter with ``@fact`` or ``@stream``, and a method is exposed as a command by
marking it with ``@query``, ``@action`` or ``@failsafe``. Unmarked members are not part of the interface.

Each decorator records presentation metadata: a label, a description and, for properties, units. An omitted
description is taken from the docstring."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

type Units = str | Callable[[Any], str]
"""Units as text, or a function of the device read once when its interface is built."""

type StreamTier = Literal["fast", "normal", "slow"]
"""The rate at which a streamed property is polled and published. The controller sets the interval of each tier."""

type Intent = Literal["query", "action", "failsafe"]
"""What a command is for."""

_MARK = "__rigup_mark"


@dataclass(frozen=True)
class PropMark:
    """The metadata a property decorator records. ``stream`` is the polling tier, or ``None`` for a fact."""

    label: str | None
    desc: str | None
    units: Units | None
    stream: StreamTier | None


@dataclass(frozen=True)
class CommandMark:
    intent: Intent
    label: str | None
    desc: str | None


def _property[F: Callable[..., Any]](name: str, mark: PropMark) -> Callable[[F], F]:
    def decorator(getter: F) -> F:
        if isinstance(getter, property):
            made = type(getter).__name__
            raise TypeError(
                f"@{name} got a {made}, not a function: put @{name} under @number, @integer, @choice or @property"
            )
        getter.__dict__[_MARK] = mark
        return getter

    return decorator


def fact[F: Callable[..., Any]](
    *, label: str | None = None, desc: str | None = None, units: Units | None = None
) -> Callable[[F], F]:
    """Expose a property whose value is constant while the device is open. It is read once and cannot have a setter.
    Apply it below ``@property``."""
    return _property("fact", PropMark(label, desc, units, None))


def stream[F: Callable[..., Any]](
    tier: StreamTier = "normal", *, label: str | None = None, desc: str | None = None, units: Units | None = None
) -> Callable[[F], F]:
    """Expose a property whose value can change. The controller polls it at ``tier`` and publishes it when it changes.
    Apply it below ``@property``, ``@number``, ``@integer`` or ``@choice``."""
    return _property("stream", PropMark(label, desc, units, tier))


def _command[F: Callable[..., Any]](intent: Intent, label: str | None, desc: str | None) -> Callable[[F], F]:
    def decorator(method: F) -> F:
        method.__dict__[_MARK] = CommandMark(intent, label, desc)
        return method

    return decorator


def query[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a read-only command. It has no side effects, so it is safe to run at any time."""
    return _command("query", label, desc)


def action[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a command that changes hardware state. The intent is advisory: rigup does not gate the call. The
    orchestrating code decides when an action may run, for example with ``rigup.activity``."""
    return _command("action", label, desc)


def failsafe[F: Callable[..., Any]](*, label: str | None = None, desc: str | None = None) -> Callable[[F], F]:
    """Expose a command that puts the device in a safe state. It must be callable with no arguments, so the
    orchestrating code can run every failsafe on stop, on failure and on close."""

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
    "fact",
    "failsafe",
    "mark_of",
    "query",
    "stream",
]

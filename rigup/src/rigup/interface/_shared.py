"""What declarations of operations and properties share: the record a decorator leaves on a function, the error
that lists every rule a class breaks, and the description fields common to both."""

import inspect
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

_DECLARATION = "__rigup_declaration"


def declare(function: Callable[..., Any], declaration: object) -> None:
    """Leave ``declaration`` on ``function``, where :func:`declaration_of` finds it."""
    function.__dict__[_DECLARATION] = declaration


def declaration_of(function: object) -> object | None:
    """The declaration a decorator left on ``function``, or ``None``."""
    return getattr(function, "__dict__", {}).get(_DECLARATION)


class InterfaceError(TypeError):
    """A class breaks rules of its interface. ``problems`` names each one."""

    def __init__(self, owner: type, problems: list[str]) -> None:
        self.owner, self.problems = owner, problems
        if len(problems) == 1:
            super().__init__(problems[0])
        else:
            listed = "\n".join(f"- {problem}" for problem in problems)
            super().__init__(f"{owner.__name__} breaks {len(problems)} rules:\n{listed}")


def _summary(function: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(function)
    return doc.splitlines()[0].strip() if doc else None


class AttributeInfo(BaseModel):
    name: str
    label: str
    desc: str | None = None


__all__ = ["AttributeInfo", "InterfaceError", "declaration_of", "declare"]

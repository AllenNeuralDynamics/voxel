"""The problems of an instrument's files, and the error when it does not start."""

from collections.abc import Collection, Iterable
from typing import Self

from pydantic import BaseModel, ValidationError
from vxlib.schema import error_message

type ViolationLoc = tuple[str | int, ...]


class Violation(BaseModel, frozen=True):
    """One problem, with a stable code and the path to the value at fault. A check gives the path from the object it
    checks; each parent check puts its own key in front, with :meth:`Violations.under`."""

    msg: str
    code: str | None = None
    loc: ViolationLoc = ()

    @classmethod
    def not_configured(cls, label: str, name: str, *, code: str, loc: ViolationLoc) -> Self:
        """The problem of a name that the instrument file does not define."""
        return cls(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


class Violations(list[Violation]):
    """The problems that 1 check found."""

    @classmethod
    def from_validation(cls, error: ValidationError, *loc: str | int) -> Self:
        """The problems of data that did not validate, under ``loc``. The first key of ``loc`` starts each code."""
        prefix = f"{loc[0]}." if loc else ""
        return cls(
            Violation(code=f"{prefix}{found['type']}", msg=error_message(found), loc=(*loc, *found["loc"]))
            for found in error.errors()
        )

    @classmethod
    def assignments(cls, *, expected: Collection[str], assigned: Collection[str], code: str, label: str) -> Self:
        """1 problem for each key that is missing from ``assigned``, and 1 for each that is not in ``expected``.
        The path of each is its key."""
        found = cls()
        for key in sorted(set(expected) - set(assigned)):
            found.add(f"{code}.missing", f"Missing {label} assignment '{key}'.", key)
        for key in sorted(set(assigned) - set(expected)):
            found.add(f"{code}.unexpected", f"Unexpected {label} assignment '{key}'.", key)
        return found

    def add(self, code: str, msg: str, *loc: str | int) -> None:
        """Add 1 problem at ``loc``."""
        self.append(Violation(code=code, msg=msg, loc=loc))

    def under(self, *keys: str | int) -> Self:
        """These problems, with ``keys`` in front of each path."""
        return type(self)(found.model_copy(update={"loc": (*keys, *found.loc)}) for found in self)

    def codes(self) -> list[str]:
        """The code of each problem."""
        return [found.code or "" for found in self]

    def __str__(self) -> str:
        return "; ".join(found.msg for found in self)


class StartupError(Exception):
    """The instrument did not start. ``violations`` lists every problem found."""

    def __init__(self, violations: Iterable[Violation]) -> None:
        self.violations = Violations(violations)
        super().__init__(str(self.violations))


__all__ = [
    "StartupError",
    "Violation",
    "ViolationLoc",
    "Violations",
]

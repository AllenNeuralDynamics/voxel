"""Problems of a setup: each with a stable code, a message, and the place in the setup's data that it is about.

A check collects problems and returns them, or raises them as 1 pydantic ``ValidationError`` from a validator. The 2
forms convert into each other: :meth:`Problems.raise_if_any` and :meth:`Problems.from_validation`.
"""

from collections.abc import Collection
from typing import LiteralString, Self, cast

from pydantic import BaseModel, ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

from vxlib.schema import error_message

type KeyPath = tuple[str | int, ...]
"""The keys that lead to a value in nested data, such as ``("nodes", "detection", "devices", "camera")``."""


class Problem(BaseModel, frozen=True):
    """1 problem of a setup. ``loc`` is where it belongs: the value at fault for a problem in a file, the entry of the
    thing involved for a problem found later, such as a device that does not answer, or empty when it is about
    nothing in the data. ``detail`` holds more for a person who looks closer, such as the traceback of a driver that
    failed. A check gives ``loc`` from the object it checks; each parent check puts its own key in front, with
    :meth:`Problems.under`."""

    code: str
    msg: str
    loc: KeyPath = ()
    detail: str | None = None

    @classmethod
    def not_configured(cls, label: str, name: str, *, code: str, loc: KeyPath) -> Self:
        """The problem of a name that the setup does not define."""
        return cls(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


class Problems(list[Problem]):
    """The problems that 1 check found."""

    @classmethod
    def from_validation(cls, error: ValidationError, *loc: str | int) -> Self:
        """The problems of data that did not validate, under ``loc``. The first key of ``loc`` starts each code."""
        prefix = f"{loc[0]}." if loc else ""
        return cls(
            Problem(
                code=f"{prefix}{found['type']}",
                msg=error_message(found),
                loc=(*loc, *found["loc"]),
                detail=found.get("ctx", {}).get("detail"),
            )
            for found in error.errors()
        )

    @classmethod
    def assignments(cls, *, expected: Collection[str], assigned: Collection[str], code: str, label: str) -> Self:
        """1 problem for each key that is missing from ``assigned``, and 1 for each that is not in ``expected``.
        The place of each is its key."""
        found = cls()
        for key in sorted(set(expected) - set(assigned)):
            found.add(f"{code}.missing", f"Missing {label} assignment '{key}'.", key)
        for key in sorted(set(assigned) - set(expected)):
            found.add(f"{code}.unexpected", f"Unexpected {label} assignment '{key}'.", key)
        return found

    def add(self, code: str, msg: str, *loc: str | int, detail: str | None = None) -> None:
        """Add 1 problem at ``loc``."""
        self.append(Problem(code=code, msg=msg, loc=loc, detail=detail))

    def under(self, *keys: str | int) -> Self:
        """These problems, with ``keys`` in front of each place."""
        return type(self)(found.model_copy(update={"loc": (*keys, *found.loc)}) for found in self)

    def codes(self) -> list[str]:
        """The code of each problem."""
        return [found.code for found in self]

    def raise_if_any(self, title: str) -> None:
        """Raise these problems as 1 ``ValidationError`` titled ``title``, each with its code, place and detail. A
        pydantic validator calls this, so that data that does not validate reports every problem at once."""
        if not self:
            return
        details = [
            InitErrorDetails(
                type=PydanticCustomError(
                    cast("LiteralString", found.code), "{msg}", {"msg": found.msg, "detail": found.detail}
                ),
                loc=found.loc,
                input=None,
            )
            for found in self
        ]
        raise ValidationError.from_exception_data(title, details)

    def __str__(self) -> str:
        return "; ".join(found.msg for found in self)


__all__ = ["KeyPath", "Problem", "Problems"]

"""Issues: what is wrong, each with a stable code, a level, a message, and the place in the data that it is about.

A :class:`Problem` is wrong in a setup's data. Its :class:`Level` says what it refuses: a fatal problem refuses
everything, such as opening an instrument; an error refuses the next step, such as an edit or a start; a warning is
reported and refuses nothing. An :class:`Alert` is wrong in a running instrument now, and ends
by itself when the state changes back. A :class:`Failure` is what stopped a piece of work, such as an acquisition,
and stays in its record.

A check collects problems and returns them, or raises its errors as 1 pydantic ``ValidationError`` from a validator.
The 2 forms convert into each other: :meth:`Problems.raise_if_any` and :meth:`Problems.from_validation`.
"""

import traceback
from collections.abc import Collection
from datetime import datetime
from enum import IntEnum
from typing import Any, LiteralString, Self, cast

from pydantic import BaseModel, GetCoreSchemaHandler, GetJsonSchemaHandler, ValidationError
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, InitErrorDetails, PydanticCustomError, core_schema

from vxlib.schema import error_message

type KeyPath = tuple[str | int, ...]
"""The keys that lead to a value in nested data, such as ``("nodes", "detection", "devices", "camera")``."""


class Level(IntEnum):
    """What an issue refuses, ordered: a higher level refuses more. It is saved and sent as its name in lowercase,
    such as ``"error"``; the numbers only order the levels in code, with room to add one between or below."""

    WARNING = 10
    ERROR = 20
    FATAL = 30

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._parse, serialization=core_schema.plain_serializer_function_ser_schema(lambda level: level.name.lower())
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        return {"type": "string", "enum": [level.name.lower() for level in cls]}

    @classmethod
    def _parse(cls, value: object) -> "Level":
        if isinstance(value, cls):
            return value
        if isinstance(value, str) and value.upper() in cls.__members__:
            return cls[value.upper()]
        raise ValueError(f"a level is one of {', '.join(level.name.lower() for level in cls)}, not {value!r}")


class Issue(BaseModel, frozen=True):
    """Something that is wrong. ``code`` names its kind, ``level`` says how bad it is, and ``loc`` is where it
    belongs: the value at fault in a file, the entry of the thing involved, such as a device that does not answer, or
    empty when it is about nothing in the data. ``detail`` holds more for a person who looks closer, such as the
    traceback of a driver that failed."""

    code: str
    level: Level
    msg: str
    loc: KeyPath = ()
    detail: str | None = None


class Problem(Issue, frozen=True):
    """Something wrong in a setup's data, an error by default. A check gives ``loc`` from the object it checks; each
    parent check puts its own key in front, with :meth:`Problems.under`."""

    level: Level = Level.ERROR

    @classmethod
    def not_configured(cls, label: str, name: str, *, code: str, loc: KeyPath) -> Self:
        """The problem of a name that the setup does not define."""
        return cls(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


class Alert(Issue, frozen=True):
    """Something wrong with a running instrument now. It became true at ``since``, and it ends by itself when the state
    changes back. Its code and ``loc`` stay the same while it lasts."""

    since: datetime


class Failure(Issue, frozen=True):
    """What stopped a piece of work, such as an acquisition or 1 part of it. It is always an error, and it stays in
    the record of the work."""

    level: Level = Level.ERROR

    @classmethod
    def of(cls, error: BaseException, *, code: str, loc: KeyPath = ()) -> Self:
        """The failure that ``error`` describes: its kind and message as ``msg``, its traceback as ``detail``."""
        text = str(error)
        msg = f"{type(error).__name__}: {text}" if text else type(error).__name__
        return cls(code=code, msg=msg, loc=loc, detail="".join(traceback.format_exception(error)))


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

    def add(self, code: str, msg: str, *loc: str | int, detail: str | None = None, level: Level = Level.ERROR) -> None:
        """Add 1 problem at ``loc``."""
        self.append(Problem(code=code, msg=msg, loc=loc, detail=detail, level=level))

    def errors(self) -> Self:
        """The problems that refuse something: the fatal ones and the errors, without the warnings."""
        return type(self)(found for found in self if found.level >= Level.ERROR)

    def fatal(self) -> Self:
        """The problems that refuse everything."""
        return type(self)(found for found in self if found.level is Level.FATAL)

    def as_fatal(self) -> Self:
        """These problems, each error made fatal: for a check whose every error refuses everything. Warnings stay."""
        return type(self)(
            found.model_copy(update={"level": Level.FATAL}) if found.level is Level.ERROR else found for found in self
        )

    def under(self, *keys: str | int) -> Self:
        """These problems, with ``keys`` in front of each place."""
        return type(self)(found.model_copy(update={"loc": (*keys, *found.loc)}) for found in self)

    def codes(self) -> list[str]:
        """The code of each problem."""
        return [found.code for found in self]

    def raise_if_any(self, title: str) -> None:
        """Raise the errors among these problems as 1 ``ValidationError`` titled ``title``, each with its code, place
        and detail; warnings refuse nothing, so they are not raised. A pydantic validator calls this, so that data that
        does not validate reports every error at once."""
        errors = self.errors()
        if not errors:
            return
        details = [
            InitErrorDetails(
                type=PydanticCustomError(
                    cast("LiteralString", found.code), "{msg}", {"msg": found.msg, "detail": found.detail}
                ),
                loc=found.loc,
                input=None,
            )
            for found in errors
        ]
        raise ValidationError.from_exception_data(title, details)

    def __str__(self) -> str:
        return "; ".join(found.msg for found in self)


__all__ = ["Alert", "Failure", "Issue", "KeyPath", "Level", "Problem", "Problems"]

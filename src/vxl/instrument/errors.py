"""Structured validation results and expected instrument failures."""

from collections.abc import Collection
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

from vxlib import load_yaml

type ViolationLoc = tuple[str | int, ...]


class Violation(BaseModel, frozen=True):
    """One structured validation or startup failure."""

    msg: str
    code: str | None = None
    loc: ViolationLoc = ()


def assignment_violations(
    *,
    expected: Collection[str],
    assigned: Collection[str],
    loc: ViolationLoc,
    code: str,
    label: str,
) -> list[Violation]:
    """Return precise missing and unexpected key violations for one assignment mapping."""
    expected_keys = set(expected)
    assigned_keys = set(assigned)
    return [
        *(
            Violation(
                code=f"{code}.missing",
                msg=f"Missing {label} assignment '{key}'.",
                loc=(*loc, key),
            )
            for key in sorted(expected_keys - assigned_keys)
        ),
        *(
            Violation(
                code=f"{code}.unexpected",
                msg=f"Unexpected {label} assignment '{key}'.",
                loc=(*loc, key),
            )
            for key in sorted(assigned_keys - expected_keys)
        ),
    ]


class Loaded[T: BaseModel](BaseModel, frozen=True):
    """A persisted model that was found, read, and validated."""

    status: Literal["loaded"] = "loaded"
    value: T


class Missing(BaseModel, frozen=True):
    """A persisted model whose file was not found."""

    status: Literal["missing"] = "missing"


class Invalid(BaseModel, frozen=True):
    """A persisted model whose file could not be read or validated."""

    status: Literal["invalid"] = "invalid"


type Inspected[T: BaseModel] = Annotated[Loaded[T] | Missing | Invalid, Field(discriminator="status")]


def inspect_model[T: BaseModel](
    path: Path,
    model: type[T],
    source: str,
) -> tuple[Inspected[T], tuple[Violation, ...]]:
    """Load a persisted model, returning structured violations instead of raising."""
    try:
        return Loaded(value=load_yaml(path, model)), ()
    except FileNotFoundError:
        return Missing(), ()
    except ValidationError as exc:
        return Invalid(), tuple(
            Violation(
                code=f"{source}.{error['type']}",
                msg=error["msg"],
                loc=(source, *error["loc"]),
            )
            for error in exc.errors()
        )
    except Exception as exc:
        return Invalid(), (Violation(code=f"{source}.load", msg=str(exc), loc=(source,)),)


class InstrumentError(Exception):
    """Base class for expected instrument failures."""


class StartupError(InstrumentError):
    """Raised when an instrument cannot finish startup."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        lines = ["Instrument startup failed:"]
        for violation in violations:
            code = f"[{violation.code}] " if violation.code else ""
            loc = ".".join(str(part) for part in violation.loc)
            location = f"{loc}: " if loc else ""
            msg = violation.msg.replace("\n", "\n    ")
            lines.append(f"  - {code}{location}{msg}")
        super().__init__("\n".join(lines))


class OperationRejectedError(InstrumentError):
    """Raised when an operation is invalid; state is unchanged."""


class InstrumentBusyError(InstrumentError):
    """Raised when an operation is unavailable in the instrument's current mode."""


__all__ = [
    "Inspected",
    "InstrumentBusyError",
    "InstrumentError",
    "Invalid",
    "Loaded",
    "Missing",
    "OperationRejectedError",
    "StartupError",
    "Violation",
    "ViolationLoc",
    "assignment_violations",
    "inspect_model",
]

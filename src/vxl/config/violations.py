"""Structured problems found when checking instrument files."""

from collections.abc import Collection

from pydantic import BaseModel

type ViolationLoc = tuple[str | int, ...]


class Violation(BaseModel, frozen=True):
    """One problem, with a stable code and the path to the value at fault."""

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
    """Return 1 violation for each key that is missing from ``assigned`` or not in ``expected``."""
    expected_keys = set(expected)
    assigned_keys = set(assigned)
    return [
        *(
            Violation(code=f"{code}.missing", msg=f"Missing {label} assignment '{key}'.", loc=(*loc, key))
            for key in sorted(expected_keys - assigned_keys)
        ),
        *(
            Violation(code=f"{code}.unexpected", msg=f"Unexpected {label} assignment '{key}'.", loc=(*loc, key))
            for key in sorted(assigned_keys - expected_keys)
        ),
    ]


def not_configured(label: str, name: str, *, code: str, loc: ViolationLoc) -> Violation:
    """A violation for a reference to something the instrument file does not define."""
    return Violation(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


__all__ = ["Violation", "ViolationLoc", "assignment_violations", "not_configured"]

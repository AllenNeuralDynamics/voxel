"""The problems of an instrument's files, and the error when it does not start."""

from collections.abc import Collection, Iterable

from pydantic import BaseModel

type ViolationLoc = tuple[str | int, ...]


class Violation(BaseModel, frozen=True):
    """One problem, with a stable code and the path to the value at fault. A check gives the path from the object it
    checks; each parent check puts its own key in front, with :func:`under`."""

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
    """A violation for a name the instrument file does not define."""
    return Violation(code=code, msg=f"{label} '{name}' is not configured.", loc=loc)


def under(keys: ViolationLoc, violations: Iterable[Violation]) -> list[Violation]:
    """Each of ``violations``, with ``keys`` in front of its path."""
    return [violation.model_copy(update={"loc": (*keys, *violation.loc)}) for violation in violations]


class StartupError(Exception):
    """The instrument did not start. ``violations`` lists every problem found."""

    def __init__(self, violations: list[Violation]) -> None:
        super().__init__("; ".join(violation.msg for violation in violations))
        self.violations = violations


__all__ = [
    "StartupError",
    "Violation",
    "ViolationLoc",
    "assignment_violations",
    "not_configured",
    "under",
]

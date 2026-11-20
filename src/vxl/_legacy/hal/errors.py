"""Structured validation errors and expected HAL failures."""

from collections.abc import Collection

from pydantic import BaseModel

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


class HALError(Exception):
    """Base class for expected HAL failures."""


class HALStartupError(HALError):
    """Raised when the hardware runtime cannot finish startup."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        lines = ["Hardware startup failed:"]
        for violation in violations:
            code = f"[{violation.code}] " if violation.code else ""
            loc = ".".join(str(part) for part in violation.loc)
            location = f"{loc}: " if loc else ""
            msg = violation.msg.replace("\n", "\n    ")
            lines.append(f"  - {code}{location}{msg}")
        super().__init__("\n".join(lines))


__all__ = [
    "HALError",
    "HALStartupError",
    "Violation",
    "ViolationLoc",
    "assignment_violations",
]

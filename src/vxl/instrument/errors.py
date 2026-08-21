"""Structured validation errors and expected instrument failures."""

from vxl.hal.errors import Violation, ViolationLoc, assignment_violations


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
    "InstrumentBusyError",
    "InstrumentError",
    "OperationRejectedError",
    "StartupError",
    "Violation",
    "ViolationLoc",
    "assignment_violations",
]

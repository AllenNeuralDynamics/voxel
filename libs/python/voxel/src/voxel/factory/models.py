from enum import StrEnum

from pydantic import BaseModel

from voxel.reporting.errors import ErrorInfo, ResultsReportEntry, tabulate_report


class SpinnerErrorType(StrEnum):
    # Module and class loading
    MODULE = "module_error"
    CLASS = "class_not_found"

    # Dependency resolution
    DEPENDENCY = "dependency_failed"

    # Instance creation
    ARGS = "args_mismatch"
    KWARGS = "kwargs_mismatch"
    INIT = "instantiation_error"

    # File and data loading
    FILE = "file_error"  # File not found, permission denied, etc.
    PARSE = "parse_error"  # JSON/YAML syntax errors
    SCHEMA = "schema_error"  # Invalid data structure/missing fields
    VALIDATION = "validation_error"  # BuildSpec validation failed

    # General
    OTHER = "other"

    @classmethod
    def from_type_error(cls, error: TypeError) -> "SpinnerErrorType":
        """Classify TypeError by examining error message."""
        msg = str(error)
        if "positional" in msg:
            return cls.ARGS
        elif "keyword" in msg or "unexpected" in msg:
            return cls.KWARGS
        else:
            return cls.INIT


class SpinnerResults[T](BaseModel):
    items: dict[str, T]
    errors: dict[str, ErrorInfo]

    def ok(self) -> bool:
        """Check if the build was successful (no errors)."""
        return not self.errors

    def report(self) -> dict[str, ResultsReportEntry]:
        results = {}
        for name in self.items:
            results[name] = ResultsReportEntry(
                status="OK",
                category="✓",
                message=f"Built {name} successfully",
            )
        for name, error in self.errors.items():
            results[name] = ResultsReportEntry(
                status="ERROR",
                category=error.category,
                message=error.message,
            )
        return results

    def __repr__(self) -> str:
        """String representation of the results."""
        return tabulate_report(self.report())

    def __add__(self, other: "SpinnerResults[T]") -> "SpinnerResults[T]":
        """Combine two SpinnerResults instances."""
        if not isinstance(other, SpinnerResults):
            raise TypeError("Can only add SpinnerResults instances")

        combined_data = {**self.items, **other.items}
        combined_errors = {**self.errors, **other.errors}

        return SpinnerResults(items=combined_data, errors=combined_errors)

"""Error handling and validation utilities."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class IErrorInfo:
    """Protocol for structured error information."""

    name: str
    category: str | StrEnum
    message: str
    details: dict[str, Any]


class ErrorInfo(BaseModel):
    """Structured error information."""

    name: str
    category: str | StrEnum
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


MAX_INPUT_REPR_LENGTH = 100


def pydantic_to_error_info(validation_error: ValidationError, base_name: str = 'validation') -> dict[str, ErrorInfo]:
    """Convert Pydantic ValidationError to a dict of ErrorInfo objects keyed by error name.

    Args:
        validation_error: The Pydantic ValidationError to convert
        base_name: Base name for the error (e.g., "system_definition")

    Returns:
        Dict of ErrorInfo objects, keyed by error name

    """
    errors = {}

    for error in validation_error.errors():
        # Build descriptive name from location path
        loc_path = '.'.join(str(part) for part in error['loc'])
        name = f'{base_name}.{loc_path}' if loc_path else base_name

        # Use Pydantic's error type directly - no mapping needed!
        error_type = error['type']  # e.g., "string_type", "int_parsing", "missing"

        # Enhanced message with context
        message = error['msg']
        if 'input' in error:
            # Only show input if it's reasonably sized to avoid noise
            input_repr = repr(error['input'])
            if len(input_repr) < MAX_INPUT_REPR_LENGTH:  # Keep it reasonable
                message += f' (received: {input_repr})'

        errors[name] = ErrorInfo(
            name=name,
            category=error_type,
            message=message,
            details=error.get('ctx', {}),  # Additional context if available
        )

    return errors


class ResultsReportEntry(BaseModel):
    status: Literal['OK', 'ERROR']
    category: str
    message: str

    @field_validator('category', mode='before')
    @classmethod
    def validate_category(cls, value: Any) -> str:
        return str(value)


def tabulate_report(report: dict[str, ResultsReportEntry]) -> str:
    """Tabulate a report dictionary into a string."""
    # Calculate column widths
    name_width = max(len(item) for item in report)
    name_width = max(name_width, len('Name'))

    status_width = max(len(item.status) for item in report.values())
    status_width = max(status_width, len('Status'))

    # Handle None values for category
    category_values = [item.category or '' for item in report.values()]
    category_width = max(len(val) for val in category_values)
    category_width = max(category_width, len('Category'))

    # Handle None values for message
    message_values = [item.message or '' for item in report.values()]
    message_width = max(len(val) for val in message_values)
    message_width = max(message_width, len('Message'))
    message_width = min(message_width, 100)  # Cap message width for readability

    lines = []
    header = (
        f'{"Name":<{name_width}} | '
        f'{"Status":<{status_width}} | '
        f'{"Category":<{category_width}} | '
        f'{"Message":<{message_width}}'
    )
    lines.append(header)
    lines.append('-' * len(header))
    for name, item in report.items():
        line = (
            f'{name:<{name_width}} | '
            f'{item.status:<{status_width}} | '
            f'{item.category!s:<{category_width}} | '
            f'{item.message:<{message_width}}'
        )
        lines.append(line)
    return '\n'.join(lines)

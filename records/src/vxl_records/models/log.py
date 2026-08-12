"""Structured entries in the ordered operational log journal."""

from datetime import datetime

from pydantic import AwareDatetime, Field, JsonValue

from ._base import RecordModel


class LogException(RecordModel):
    """Transport-safe exception details captured from one log record."""

    kind: str = Field(min_length=1)
    message: str
    traceback: str
    truncated: bool = False


class LogEntry(RecordModel):
    """One durably ordered diagnostic record."""

    seq: int = Field(ge=1)
    emitted_at: AwareDatetime
    recorded_at: AwareDatetime
    level: int = Field(ge=0)
    logger: str = Field(min_length=1)
    message: str
    node_id: str | None = Field(default=None, min_length=1)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    exception: LogException | None = None

    @property
    def latency(self) -> float:
        """Seconds between source emission and durable journal recording."""
        return (self.recorded_at - self.emitted_at).total_seconds()


def unix_time_us(value: datetime) -> int:
    """Convert an aware datetime to integer microseconds since the Unix epoch."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return int(value.timestamp() * 1_000_000)

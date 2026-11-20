"""Errors of the station's records."""

from vxlib.issues import Failure


class RecordsError(RuntimeError):
    """A failure of the records."""


class DatabaseError(RecordsError):
    """The records database belongs to another program, has a newer schema, or misses a migration."""


class AcquisitionNotFoundError(RecordsError, LookupError):
    """No acquisition has the given id."""


class CaptureError(Exception):
    """An error of an acquisition that knows its own failure: its code, and the device it is about."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.msg)
        self.failure = failure

"""Errors raised by durable Voxel record operations."""


class RecordsError(RuntimeError):
    """Base class for Voxel record failures."""


class DatabaseIdentityError(RecordsError):
    """Raised when a SQLite file belongs to another application."""


class DatabaseVersionError(RecordsError):
    """Raised when a records database uses an unsupported schema version."""


class ManifestExistsError(RecordsError):
    """Raised when creating an acquisition whose ID already exists."""


class ManifestNotFoundError(RecordsError):
    """Raised when an acquisition or volume cannot be found."""


class RevisionConflictError(RecordsError):
    """Raised when acquisition revision expectations are violated."""


class InvalidTransitionError(RecordsError):
    """Raised when an acquisition object cannot enter the requested lifecycle state."""


class ManifestSyncError(RecordsError):
    """Raised when a committed record cannot be projected beside its acquisition data."""


class LegacyImportError(RecordsError):
    """Raised when a legacy file catalog cannot be imported safely."""

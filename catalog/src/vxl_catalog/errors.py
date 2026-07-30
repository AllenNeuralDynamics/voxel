"""Catalog operation errors."""


class CatalogError(RuntimeError):
    """Base class for catalog failures."""


class ManifestExistsError(CatalogError):
    """Raised when creating an acquisition that already exists."""


class ManifestNotFoundError(CatalogError):
    """Raised when an acquisition or one of its nested resources does not exist."""


class RevisionConflictError(CatalogError):
    """Raised when a manifest changed since the caller's expected revision."""


class InvalidTransitionError(CatalogError):
    """Raised when a lifecycle operation requests an invalid state transition."""


class ManifestSyncError(CatalogError):
    """Raised when the catalog index commits but the acquisition-root manifest cannot be written."""

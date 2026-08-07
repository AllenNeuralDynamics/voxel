"""Transport-independent preview processing service."""

from pathlib import Path


class PreviewWorkspace:
    """Own snapshot and inpainting behavior for one preview-service deployment.

    The service is intentionally not attached to an instrument yet. Its feed
    lifecycle and snapshot API will be added once those contracts are settled.
    Construction does not create the configured storage directory.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        """Directory under which preview-service artifacts will be stored."""
        return self._root


__all__ = ["PreviewWorkspace"]

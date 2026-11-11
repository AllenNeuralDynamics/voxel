"""Local instrument-template discovery for Voxel station applications."""

import logging
from pathlib import Path

from vxl.instrument import InstrumentConfig, InstrumentStore
from vxl.instrument.store import Loaded

_BUILTIN_TEMPLATES_DIR = Path(__file__).parent / "builtins"
log = logging.getLogger(__name__)


class InstrumentTemplates:
    """Discover validated instrument configurations from one template directory."""

    def __init__(self, directory: Path | str = _BUILTIN_TEMPLATES_DIR) -> None:
        self._directory = Path(directory)

    @property
    def directory(self) -> Path:
        """Directory containing ``*.voxel.yaml`` instrument templates."""
        return self._directory

    def discover(self) -> dict[str, InstrumentConfig]:
        """Return valid templates while logging every invalid configuration."""
        found: dict[str, InstrumentConfig] = {}
        if not self._directory.is_dir():
            return found

        for path in sorted(self._directory.glob("*.voxel.yaml")):
            name = path.name.removesuffix(".voxel.yaml")
            inspected = InstrumentStore.load_config(path)
            if inspected.ok and isinstance(inspected.config, Loaded):
                found[name] = inspected.config.value
                continue
            log.warning(
                "Skipping instrument template '%s': %s",
                path.name,
                "; ".join(violation.msg for violation in inspected.violations),
            )
        return found

    def get(self, name: str) -> InstrumentConfig:
        """Return one valid template or raise when it is unavailable."""
        if (template := self.discover().get(name)) is None:
            raise KeyError(f"No instrument template '{name}'")
        return template


__all__ = ["InstrumentTemplates"]

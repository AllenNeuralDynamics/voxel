"""System configuration for SPIM Studio.

Manages the ~/.spim/ directory structure:
- system.yaml: Global settings with session roots
- rigs/: Rig config templates
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from ruyaml import YAML

log = logging.getLogger(__name__)

SPIM_DIR = Path.home() / ".spim"
SYSTEM_CONFIG_FILE = SPIM_DIR / "system.yaml"
RIGS_DIR = SPIM_DIR / "rigs"
SESSION_FILENAME = "session.spim.yaml"

yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


class SessionRoot(BaseModel):
    """A directory where sessions can be created."""

    name: str
    path: Path
    label: str | None = None
    description: str | None = None

    def get_label(self) -> str:
        """Get display label, falling back to name."""
        return self.label or self.name


class SessionDirectory(BaseModel):
    """A session discovered by scanning a root."""

    name: str  # Folder name
    path: Path  # Full path to session dir
    root_name: str  # Which root it's in
    rig_name: str  # From session.spim.yaml rig.info.name
    modified: datetime  # Last modified time of session.spim.yaml


class SystemConfig(BaseModel):
    """Global system configuration from ~/.spim/system.yaml."""

    session_roots: list[SessionRoot] = Field(default_factory=list)

    @classmethod
    def load(cls) -> SystemConfig:
        """Load from ~/.spim/system.yaml, create defaults if missing."""
        if not SYSTEM_CONFIG_FILE.exists():
            log.info("First run detected, creating ~/.spim/ directory structure")
            cls._create_defaults()

        with open(SYSTEM_CONFIG_FILE) as f:
            data = yaml.load(f) or {}

        roots = []
        for root_data in data.get("session_roots", []):
            path = Path(root_data["path"]).expanduser().resolve()
            roots.append(
                SessionRoot(
                    name=root_data["name"],
                    path=path,
                    label=root_data.get("label"),
                    description=root_data.get("description"),
                )
            )

        return cls(session_roots=roots)

    @classmethod
    def _create_defaults(cls) -> None:
        """Create default ~/.spim/ directory structure on first run."""
        # Create directories
        SPIM_DIR.mkdir(parents=True, exist_ok=True)
        RIGS_DIR.mkdir(exist_ok=True)

        # Create session root directories
        experiments_dir = SPIM_DIR / "experiments"
        playground_dir = SPIM_DIR / "playground"
        experiments_dir.mkdir(exist_ok=True)
        playground_dir.mkdir(exist_ok=True)

        # Copy example rig configs from package
        examples_dir = Path(__file__).parent / "examples"
        rig_files = [
            "simulated.local.rig.yaml",
            "simulated.distributed.rig.yaml",
            "simulated.hybrid.rig.yaml",
        ]
        for rig_file in rig_files:
            src = examples_dir / rig_file
            dst = RIGS_DIR / rig_file
            if src.exists() and not dst.exists():
                shutil.copy(src, dst)
                log.info(f"Created rig config: {dst}")

        # Create system.yaml with default session roots
        system_yaml = {
            "session_roots": [
                {
                    "name": "playground",
                    "label": "Playground",
                    "description": "Test and development sessions",
                    "path": str(playground_dir),
                },
                {
                    "name": "experiments",
                    "label": "Experiments",
                    "description": "Production experiment sessions",
                    "path": str(experiments_dir),
                },
            ]
        }
        with open(SYSTEM_CONFIG_FILE, "w") as f:
            yaml.dump(system_yaml, f)
        log.info(f"Created system config: {SYSTEM_CONFIG_FILE}")

    def get_root(self, name: str) -> SessionRoot | None:
        """Get root by name."""
        for root in self.session_roots:
            if root.name == name:
                return root
        return None

    def list_sessions(self, root_name: str) -> list[SessionDirectory]:
        """Scan root for existing sessions.

        Scans immediate children of the root for directories containing session.spim.yaml.
        """
        root = self.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")

        if not root.path.exists():
            log.warning(f"Session root path does not exist: {root.path}")
            return []

        sessions: list[SessionDirectory] = []
        for child in root.path.iterdir():
            if not child.is_dir():
                continue

            session_file = child / SESSION_FILENAME
            if not session_file.exists():
                continue

            try:
                with open(session_file) as f:
                    data = yaml.load(f) or {}

                rig_info = data.get("rig", {}).get("info", {})
                rig_name = rig_info.get("name", "Unknown")
                modified = datetime.fromtimestamp(session_file.stat().st_mtime)

                sessions.append(
                    SessionDirectory(
                        name=child.name,
                        path=child,
                        root_name=root_name,
                        rig_name=rig_name,
                        modified=modified,
                    )
                )
            except Exception as e:
                log.warning(f"Failed to read session {child}: {e}")

        # Sort by modified time, most recent first
        sessions.sort(key=lambda s: s.modified, reverse=True)
        return sessions


def list_rigs() -> list[str]:
    """List available rig configs from ~/.spim/rigs/.

    Returns list of rig names (filename without .rig.yaml extension).
    """
    if not RIGS_DIR.exists():
        return []

    rigs = []
    for path in RIGS_DIR.glob("*.rig.yaml"):
        name = path.name.removesuffix(".rig.yaml")
        rigs.append(name)

    rigs.sort()
    return rigs


def get_rig_path(name: str) -> Path | None:
    """Get full path to a rig config by name."""
    path = RIGS_DIR / f"{name}.rig.yaml"
    if path.exists():
        return path
    return None

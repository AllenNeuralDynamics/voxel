"""System configuration for Voxel.

Manages the ~/.voxel/ directory structure:
- system.yaml: Global settings with session roots
- rigs/: Rig config templates
"""

import logging
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field
from ruyaml import YAML

from vxl.session import SessionConfig

log = logging.getLogger(__name__)

VOXEL_DIR = Path.home() / ".voxel"
SYSTEM_CONFIG_FILE = VOXEL_DIR / "system.yaml"
RIGS_DIR = VOXEL_DIR / "rigs"
SESSION_FILENAME = "session.voxel.yaml"

yaml = YAML()
yaml.preserve_quotes = True  # type: ignore[assignment]


def slugify(name: str) -> str:
    """Convert a display name to a filesystem-friendly slug."""
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


class SessionRoot(BaseModel):
    """A directory where sessions can be created."""

    name: str
    path: Path
    label: str | None = None
    description: str | None = None

    def get_label(self) -> str:
        """Get display label, falling back to name."""
        return self.label or self.name

    def session_path(self, session_name: str) -> Path:
        """Convert a display name to a full session directory path."""
        return self.path / slugify(session_name)


class SessionDirectory(BaseModel):
    """Filesystem facts about a session directory."""

    name: str
    path: Path
    root_name: str
    modified: datetime


class SessionListing(BaseModel):
    """Session directory with parsed config or errors, for listing."""

    directory: SessionDirectory
    config: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class SystemConfig(BaseModel):
    """Global system configuration from ~/.voxel/system.yaml."""

    session_roots: list[SessionRoot] = Field(default_factory=list)

    @classmethod
    def load(cls) -> Self:
        """Load from ~/.voxel/system.yaml, create defaults if missing."""
        if not SYSTEM_CONFIG_FILE.exists():
            log.info("First run detected, creating ~/.voxel/ directory structure")
            cls._create_defaults()

        with SYSTEM_CONFIG_FILE.open() as f:
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
                ),
            )

        return cls(session_roots=roots)

    @classmethod
    def _create_defaults(cls) -> None:
        """Create default ~/.voxel/ directory structure on first run."""
        # Create directories
        VOXEL_DIR.mkdir(parents=True, exist_ok=True)
        RIGS_DIR.mkdir(exist_ok=True)

        # Create session root directories
        experiments_dir = VOXEL_DIR / "experiments"
        playground_dir = VOXEL_DIR / "playground"
        experiments_dir.mkdir(exist_ok=True)
        playground_dir.mkdir(exist_ok=True)

        # Copy example rig configs from package
        examples_dir = Path(__file__).parent / "_configs"
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
            ],
        }
        with SYSTEM_CONFIG_FILE.open("w") as f:
            yaml.dump(system_yaml, f)
        log.info(f"Created system config: {SYSTEM_CONFIG_FILE}")

    def get_root(self, name: str) -> SessionRoot | None:
        """Get root by name."""
        for root in self.session_roots:
            if root.name == name:
                return root
        return None

    def list_sessions(self, root_name: str, limit: int = 50, offset: int = 0) -> list[SessionListing]:
        """Scan root for existing sessions with pagination.

        Scans all directories for mtime (fast stat-only), sorts, then parses
        YAML configs for the requested page in parallel.
        """
        root = self.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")

        if not root.path.exists():
            log.warning(f"Session root path does not exist: {root.path}")
            return []

        # Phase 1: fast scan — stat only, no YAML parsing
        directories: list[SessionDirectory] = []
        for child in root.path.iterdir():
            if not child.is_dir():
                continue

            session_file = child / SESSION_FILENAME
            if not session_file.exists():
                continue

            try:
                modified = datetime.fromtimestamp(session_file.stat().st_mtime)
                directories.append(
                    SessionDirectory(
                        name=child.name,
                        path=child,
                        root_name=root_name,
                        modified=modified,
                    ),
                )
            except Exception as e:
                log.warning(f"Failed to stat session {child}: {e}")

        # Sort by modified time, most recent first
        directories.sort(key=lambda s: s.modified, reverse=True)

        # Phase 2: parse configs for the requested page in parallel
        page = directories[offset : offset + limit]
        if not page:
            return []

        files = [d.path / SESSION_FILENAME for d in page]
        with ThreadPoolExecutor(max_workers=min(len(files), 8)) as pool:
            results = list(pool.map(_read_session_config, files))

        listings: list[SessionListing] = []
        for directory, result in zip(page, results, strict=True):
            config, errors = result
            listings.append(SessionListing(directory=directory, config=config, errors=errors))

        return listings

    def count_sessions(self, root_name: str) -> int:
        """Count sessions in a root without parsing YAML."""
        root = self.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")
        if not root.path.exists():
            return 0
        return sum(1 for child in root.path.iterdir() if child.is_dir() and (child / SESSION_FILENAME).exists())


def _read_session_config(session_file: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read and validate a session config from YAML. Returns (config_dict, errors)."""
    try:
        config = SessionConfig.from_yaml(session_file)
        return config.model_dump(mode="json"), []
    except Exception as e:
        log.warning(f"Failed to parse session config from {session_file}: {e}")
        return None, [str(e)]


def list_rigs() -> list[str]:
    """List available rig configs from ~/.voxel/rigs/.

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

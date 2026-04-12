"""Session store and catalog — handles persistence and discovery of session configs.

Store: owns the config lifecycle (load, hold, persist) with format-specific concerns.
Catalog: discovers sessions/templates and creates stores.
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruyaml import YAML

from vxl.config import SessionConfig, SessionInfo
from vxl.stack import StackStatus

log = logging.getLogger(__name__)


def _make_yaml() -> YAML:
    """Create a configured YAML instance for session config I/O.

    A fresh instance per operation avoids thread-safety issues
    with the YAML class's internal mutable state.
    """
    y = YAML()
    y.preserve_quotes = True  # type: ignore[assignment]
    y.width = 4096  # type: ignore[assignment]  # prevent unwanted line wrapping
    y.default_flow_style = False  # block style for new data
    y.indent(mapping=2, sequence=4, offset=2)  # standard 2-space with indented dashes
    return y


class SessionStore(ABC):
    """Base class for session config persistence."""

    @property
    @abstractmethod
    def config(self) -> SessionConfig: ...

    @abstractmethod
    def load(self) -> SessionConfig: ...

    @abstractmethod
    def save(self) -> None: ...

    async def aload(self) -> SessionConfig:
        """Async load — runs sync load in a thread."""
        return await asyncio.to_thread(self.load)

    async def asave(self) -> None:
        """Async save — runs sync save in a thread."""
        await asyncio.to_thread(self.save)


# ==================== Listing Types ====================


class SessionListing(BaseModel):
    """Session with parsed config or errors, for listing."""

    uid: str
    config: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    location: str | None = None  # Store-provided URL/path (optional)


class TemplateInfo(BaseModel):
    """Info about an available session template."""

    name: str
    path: Path
    rig_name: str = ""


# ==================== Session Catalog ====================


class SessionCatalog(ABC):
    """Abstract base for session/template discovery and store creation."""

    @abstractmethod
    def list_sessions(self) -> list[SessionListing]: ...

    @abstractmethod
    def list_templates(self) -> list[TemplateInfo]: ...

    @abstractmethod
    def fork(
        self,
        uid: str,
        info: SessionInfo,
        *,
        template: str | None = None,
        session: str | None = None,
        clear_stacks: bool = False,
    ) -> SessionStore:
        """Create a new session store from a template or existing session.

        Loads the source config, replaces info, optionally clears stacks,
        and returns a persisted store ready for use.

        Exactly one of template or session must be provided.
        """
        ...

    @abstractmethod
    def get_session_store(self, uid: str) -> SessionStore: ...

    async def afork(
        self,
        uid: str,
        info: SessionInfo,
        *,
        template: str | None = None,
        session: str | None = None,
        clear_stacks: bool = False,
    ) -> SessionStore:
        """Async fork — runs sync fork in a thread."""
        return await asyncio.to_thread(
            self.fork, uid, info, template=template, session=session, clear_stacks=clear_stacks
        )


# ==================== YAML Implementations ====================


class YamlSessionStore(SessionStore):
    """Loads and saves SessionConfig from/to a .voxel.yaml file.

    Preserves YAML anchors and aliases across round-trips by keeping
    the raw parsed dict alongside the validated Pydantic model.

    Uses atomic writes (temp file → backup → rename) to prevent
    corruption from crashes or concurrent IDE access.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._config: SessionConfig | None = None
        self._raw_data: dict[str, Any] | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> SessionConfig:
        if self._config is None:
            raise RuntimeError("Store not loaded — call load() or initialize() first")
        return self._config

    def load(self) -> SessionConfig:
        """Load config from YAML file, preserving raw data for round-trip fidelity."""
        y = _make_yaml()
        with self._path.open() as f:
            raw_data = y.load(f)

        # Strip _anchors helper key (used for defining reusable YAML anchors)
        if "_anchors" in raw_data:
            del raw_data["_anchors"]

        self._raw_data = raw_data
        self._config = SessionConfig.model_validate(raw_data)
        return self._config

    def initialize(self, config: SessionConfig, raw_data: dict[str, Any] | None = None) -> None:
        """Set config for a new session (from template or fork) and save immediately.

        Args:
            config: The validated SessionConfig.
            raw_data: Optional raw YAML dict for anchor preservation.
                      If None, the config is serialized from the model.
        """
        self._config = config
        self._raw_data = raw_data
        self.save()

    def save(self) -> None:
        """Save config to YAML, preserving anchors if available.

        Uses atomic write with fsync for crash safety:
        1. Write to temp file + fsync
        2. Backup existing file (if any)
        3. Atomically replace target with temp file
        4. Fsync directory for rename durability
        """
        if self._config is None:
            raise RuntimeError("Nothing to save — call load() or initialize() first")

        data = self._build_save_data()
        y = _make_yaml()

        temp_path = self._path.with_suffix(".yaml.tmp")
        backup_path = self._path.with_suffix(".yaml.bak")

        try:
            with temp_path.open("w") as f:
                y.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

        if self._path.exists():
            self._path.replace(backup_path)

        temp_path.replace(self._path)

        # Flush directory metadata so the rename is durable (POSIX)
        try:
            dir_fd = os.open(str(self._path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass  # Windows doesn't support O_RDONLY on directories

    def _build_save_data(self) -> dict[str, Any]:
        """Build the dict to serialize, merging model changes into raw data if available."""
        config = self._config
        assert config is not None  # noqa: S101

        acq_data = config.acq.model_dump(mode="json")
        grid_data = config.grid.model_dump(mode="json")
        stacks_data = {sid: s.model_dump(mode="json") for sid, s in config.stacks.items()}

        if self._raw_data is not None:
            self._raw_data["info"] = config.info.model_dump(mode="json")
            self._raw_data["metadata_target"] = config.metadata_target
            self._raw_data["metadata"] = config.metadata
            self._raw_data["acq"] = acq_data
            self._raw_data["grid"] = grid_data
            self._raw_data["stacks"] = stacks_data
            self._sync_rig_profiles()
            return self._raw_data

        return {
            "rig": config.rig.model_dump(mode="json"),
            "info": config.info.model_dump(mode="json"),
            "metadata_target": config.metadata_target,
            "metadata": config.metadata,
            "acq": acq_data,
            "grid": grid_data,
            "stacks": stacks_data,
        }

    def _sync_rig_profiles(self) -> None:
        """Sync mutable profile fields (grid, props, setup, rois) into raw data."""
        if self._raw_data is None or self._config is None:
            return

        rig_data = self._raw_data.get("rig", {})
        if "profiles" not in rig_data:
            return

        for profile_id, profile in self._config.rig.profiles.items():
            raw_profile = rig_data["profiles"].get(profile_id)
            if raw_profile is None:
                continue

            raw_profile["grid"] = profile.grid.model_dump()

            if profile.props:
                raw_profile["props"] = dict(profile.props)
            elif "props" in raw_profile:
                del raw_profile["props"]

            if profile.setup:
                raw_profile["setup"] = {
                    dev_id: [cmd.model_dump(mode="json") for cmd in cmds] for dev_id, cmds in profile.setup.items()
                }
            elif "setup" in raw_profile:
                del raw_profile["setup"]

            if profile.rois:
                raw_profile["rois"] = {dev_id: roi.model_dump() for dev_id, roi in profile.rois.items()}
            elif "rois" in raw_profile:
                del raw_profile["rois"]


SESSION_EXT = ".voxel.yaml"


class YamlSessionCatalog(SessionCatalog):
    """Filesystem-backed catalog using ~/.voxel/ directory structure.

    Layout:
        sessions_dir/
            <uid>/<uid>.voxel.yaml
        templates_dir/
            <name>.voxel.yaml
    """

    _BUNDLED_TEMPLATES_DIR = Path(__file__).parent / "_templates"

    def __init__(self, sessions_dir: Path, templates_dir: Path) -> None:
        self._sessions_dir = sessions_dir
        self._templates_dir = templates_dir
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._templates_dir.mkdir(parents=True, exist_ok=True)

    def list_sessions(self) -> list[SessionListing]:
        """Scan sessions directory, parse configs in parallel."""

        # Phase 1: fast scan — stat only
        entries: list[tuple[str, Path, datetime]] = []  # (uid, path, modified)
        for child in self._sessions_dir.iterdir():
            if not child.is_dir():
                continue
            session_file = child / f"{child.name}{SESSION_EXT}"
            if not session_file.exists():
                continue
            try:
                modified = datetime.fromtimestamp(session_file.stat().st_mtime)
                entries.append((child.name, session_file, modified))
            except Exception as e:
                log.warning(f"Failed to stat session {child}: {e}")

        entries.sort(key=lambda e: e[2], reverse=True)

        if not entries:
            return []

        # Phase 2: parse configs in parallel
        files = [path for _, path, _ in entries]
        with ThreadPoolExecutor(max_workers=min(len(files), 8)) as pool:
            results = list(pool.map(self._read_config, files))

        return [
            SessionListing(
                uid=uid,
                config=config,
                errors=errors,
                location=str(path.parent),
            )
            for (uid, path, _), (config, errors) in zip(entries, results, strict=True)
        ]

    def list_templates(self) -> list[TemplateInfo]:
        """List templates, user templates taking precedence over bundled ones with the same name."""
        by_name: dict[str, TemplateInfo] = {}
        if self._BUNDLED_TEMPLATES_DIR.exists():
            for t in self._scan_templates(self._BUNDLED_TEMPLATES_DIR):
                by_name[t.name] = t
        if self._templates_dir.exists():
            for t in self._scan_templates(self._templates_dir):
                by_name[t.name] = t  # user overrides bundled
        return sorted(by_name.values(), key=lambda t: t.name)

    def fork(
        self,
        uid: str,
        info: SessionInfo,
        *,
        template: str | None = None,
        session: str | None = None,
        clear_stacks: bool = False,
    ) -> YamlSessionStore:
        if (template is None) == (session is None):
            raise ValueError("Exactly one of 'template' or 'session' must be provided")

        # Load source config
        if template is not None:
            source_config = self._load_template(template)
        else:
            source_store = self.get_session_store(session)  # type: ignore[arg-type]
            source_config = source_store.load()

        # Build new config
        stacks = {} if clear_stacks else source_config.stacks
        acq = source_config.acq.model_copy()
        if clear_stacks:
            acq.profile_order = []

        # Reset stack statuses for fork
        if not clear_stacks:
            for stack in stacks.values():
                stack.status = StackStatus.PLANNED
                stack.started_at = None
                stack.completed_at = None
                stack.skipped_at = None
                stack.output_path = None

        config = SessionConfig(
            rig=source_config.rig,
            info=info,
            metadata_target=source_config.metadata_target,
            metadata=source_config.metadata,
            acq=acq,
            grid=source_config.grid,
            stacks=stacks,
        )

        # Create store and persist
        session_dir = self._sessions_dir / uid
        session_dir.mkdir(parents=True, exist_ok=True)
        store = YamlSessionStore(session_dir / f"{uid}{SESSION_EXT}")
        store.initialize(config)
        return store

    def get_session_store(self, uid: str) -> YamlSessionStore:
        path = self._sessions_dir / uid / f"{uid}{SESSION_EXT}"
        if not path.exists():
            raise FileNotFoundError(f"No session found: {uid}")
        return YamlSessionStore(path)

    # --- Private helpers ---

    def _load_template(self, name: str) -> SessionConfig:
        """Load a template config by name. Checks user templates first, then bundled."""
        user_path = self._templates_dir / f"{name}.voxel.yaml"
        if user_path.exists():
            return self._load_yaml_config(user_path)

        if self._BUNDLED_TEMPLATES_DIR:
            bundled_path = self._BUNDLED_TEMPLATES_DIR / f"{name}.voxel.yaml"
            if bundled_path.exists():
                return self._load_yaml_config(bundled_path)

        raise FileNotFoundError(f"Template '{name}' not found")

    @staticmethod
    def _load_yaml_config(path: Path) -> SessionConfig:
        y = _make_yaml()
        with path.open() as f:
            raw = y.load(f)
        if "_anchors" in raw:
            del raw["_anchors"]
        return SessionConfig.model_validate(raw)

    @staticmethod
    def _read_config(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
        y = _make_yaml()
        try:
            with path.open() as f:
                raw = y.load(f)
            if "_anchors" in raw:
                del raw["_anchors"]
            config = SessionConfig.model_validate(raw)
            return config.model_dump(mode="json"), []
        except Exception as e:
            log.warning(f"Failed to parse session config from {path}: {e}")
            return None, [str(e)]

    @staticmethod
    def _scan_templates(directory: Path) -> list[TemplateInfo]:
        templates: list[TemplateInfo] = []
        for path in sorted(directory.glob("*.voxel.yaml")):
            name = path.name.removesuffix(".voxel.yaml")
            rig_name = ""
            try:
                y = _make_yaml()
                with path.open() as f:
                    raw = y.load(f)
                rig_name = raw.get("rig", {}).get("info", {}).get("name", "")
            except Exception:
                log.warning(f"Failed to parse template {path}")
            templates.append(TemplateInfo(name=name, path=path, rig_name=rig_name))
        return templates

    def seed_templates(self) -> None:
        """Copy bundled templates to user templates directory if not already present."""
        if not self._BUNDLED_TEMPLATES_DIR or not self._BUNDLED_TEMPLATES_DIR.exists():
            return
        import shutil  # noqa: PLC0415

        for src in self._BUNDLED_TEMPLATES_DIR.glob("*.voxel.yaml"):
            dst = self._templates_dir / src.name
            if not dst.exists():
                shutil.copy(src, dst)
                log.info(f"Seeded template: {dst.name}")

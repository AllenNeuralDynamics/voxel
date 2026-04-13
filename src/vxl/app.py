"""Voxel application — lifecycle orchestrator for sessions.

Manages system configuration (data roots) and active session lifecycle.
Session/template discovery is delegated to the injected SessionCatalog.
"""

import getpass
import logging
import platform
import secrets
from datetime import UTC, datetime
from pathlib import Path

from vxl.config import DataRoot, SessionInfo
from vxl.rig import VoxelRig
from vxl.session import Session
from vxl.store import SessionCatalog, SessionStore, YamlSessionCatalog
from vxl.system import VOXEL_DIR, SystemConfig
from vxlib import slugify

log = logging.getLogger(__name__)


class VoxelApp:
    """Application-level orchestrator for Voxel sessions.

    Manages:
    - System configuration (data roots) — always local
    - Active session lifecycle (create, resume, close) — via catalog
    """

    def __init__(self, catalog: SessionCatalog | None = None) -> None:
        """Construct VoxelApp.

        Args:
            catalog: Optional explicit catalog. Primarily for tests or alternate
                backends. When omitted, defaults to a YAML catalog rooted at
                ``~/.voxel/`` with templates pre-seeded.
        """
        if catalog is None:
            catalog = YamlSessionCatalog(
                sessions_dir=VOXEL_DIR / "sessions",
                templates_dir=VOXEL_DIR / "templates",
            )
            catalog.seed_templates()

        self._system_config = SystemConfig.load()
        self._catalog = catalog
        self._session: Session | None = None
        self._store: SessionStore | None = None

    @property
    def system_config(self) -> SystemConfig:
        return self._system_config

    @property
    def catalog(self) -> SessionCatalog:
        return self._catalog

    @property
    def data_roots(self) -> list[DataRoot]:
        return self._system_config.data_roots

    @property
    def session(self) -> Session | None:
        return self._session

    @property
    def has_session(self) -> bool:
        return self._session is not None

    # ==================== Data Root Helpers ====================

    def get_data_root(self, name: str) -> DataRoot | None:
        for root in self._system_config.data_roots:
            if root.name == name:
                return root
        return None

    def get_default_data_root(self) -> DataRoot | None:
        for root in self._system_config.data_roots:
            if root.default:
                return root
        return self._system_config.data_roots[0] if self._system_config.data_roots else None

    # ==================== Session Lifecycle ====================

    async def create_session(
        self,
        *,
        template: str | None = None,
        source_session: str | None = None,
        data_root_name: str | None = None,
        name: str = "",
        description: str = "",
        collection: str = "",
        clear_stacks: bool = False,
    ) -> Session:
        """Create a new session from a template or fork from an existing session.

        Args:
            template: Template name to create from.
            source_session: Session UID to fork from.
            data_root_name: DataRoot name for acquired data. Uses default if None.
            name: Display name for the session.
            description: Session description.
            collection: Organizational grouping.
            clear_stacks: If forking, whether to clear stacks.
        """
        if self._session is not None:
            raise RuntimeError("A session is already active. Close it first.")

        # Resolve data root
        data_root = self.get_data_root(data_root_name) if data_root_name else self.get_default_data_root()

        # Generate UID — load source to get rig name for the slug
        now = datetime.now(tz=UTC)
        date = now.date().isoformat()
        suffix = slugify(name) if name else secrets.token_hex(3)

        # We need the rig name for the UID slug, but we don't have it yet.
        # Use the template/session name as a fallback for now, the catalog
        # will load the actual config.
        source_name = template or source_session or "session"
        uid = f"{slugify(source_name)}-{date}-{suffix}"

        # Resolve data path
        data_path = ""
        if data_root:
            resolved = data_root.path.expanduser().resolve() / uid
            data_path = str(resolved)

        # Build session info
        info = SessionInfo(
            uid=uid,
            name=name,
            description=description,
            source=template or source_session or "",
            created_at=now,
            created_by=getpass.getuser(),
            hostname=platform.node(),
            data_root=data_root.name if data_root else "",
            data_path=data_path,
            collection=collection,
            last_opened=now,
            open_count=1,
        )

        # Fork via catalog (async — YAML I/O runs in a thread)
        store = await self._catalog.afork(
            uid,
            info,
            template=template,
            session=source_session,
            clear_stacks=clear_stacks,
        )
        config = store.config

        # Create data directory
        if data_path:
            Path(data_path).mkdir(parents=True, exist_ok=True)

        # Start rig
        rig = VoxelRig(config=config.rig)
        await rig.start()

        self._store = store
        self._session = Session(config=config, store=store, rig=rig)
        log.info(f"Session created: {uid}")
        return self._session

    async def resume_session(self, uid: str) -> Session:
        """Resume an existing session by UID."""
        if self._session is not None:
            raise RuntimeError("A session is already active. Close it first.")

        store = self._catalog.get_session_store(uid)
        config = await store.aload()

        # Update lifecycle fields
        config.info.last_opened = datetime.now(tz=UTC)
        config.info.open_count += 1

        # Start rig
        rig = VoxelRig(config=config.rig)
        await rig.start()

        self._store = store
        self._session = Session(config=config, store=store, rig=rig)
        await store.asave()
        log.info(f"Resumed session: {uid} ({config.info.open_count} opens)")
        return self._session

    async def close_session(self) -> None:
        """Close the active session."""
        if self._session is None:
            raise RuntimeError("No active session to close")

        try:
            await self._session.close()
            log.info(f"Session closed: {self._session.config.info.uid}")
        finally:
            self._session = None
            self._store = None

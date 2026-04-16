"""Voxel Qt application coordinator.

Wraps the core VoxelApp with Qt signals and store management.
Manages child stores (devices, preview, grid, stage) that need
Qt-specific lifecycle handling.
"""

import logging
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QObject, Signal

from vxl.app import VoxelApp as CoreVoxelApp
from vxl.store import SessionListing, TemplateInfo
from vxl.system import DataRoot
from vxl_qt.store import DevicesStore, GridStore, PreviewStore, StageStore

if TYPE_CHECKING:
    from vxl import Session
    from vxl.microscope import Microscope

log = logging.getLogger(__name__)

AppPhase = Literal["idle", "launching", "ready"]


class VoxelApp(QObject):
    """Qt wrapper around the core VoxelApp.

    Adds:
    - Qt signals for state change notifications
    - Child stores (devices, preview, grid, stage)
    - Phase transitions (idle -> launching -> ready)
    """

    phase_changed = Signal(str)
    session_changed = Signal(object)
    error_changed = Signal(str)
    devices_ready = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._phase: AppPhase = "idle"
        self._error: str = ""

        self._core = CoreVoxelApp()

        # Child stores
        self.devices = DevicesStore(parent=self)
        self.preview = PreviewStore(parent=self)
        self.grid = GridStore(parent=self)
        self.stage = StageStore(parent=self)

        log.info("VoxelApp initialized with %d data roots", len(self._core.data_roots))

    def _set_phase(self, phase: AppPhase) -> None:
        if self._phase != phase:
            self._phase = phase
            log.debug("Phase changed: %s", phase)
            self.phase_changed.emit(phase)

    def _set_error(self, error: str) -> None:
        self._error = error
        self.error_changed.emit(error)

    # ==================== Properties ====================

    @property
    def phase(self) -> AppPhase:
        return self._phase

    @property
    def session(self) -> "Session | None":
        return self._core.session

    @property
    def microscope(self) -> "Microscope | None":
        s = self._core.session
        return s.microscope if s else None

    @property
    def error(self) -> str:
        return self._error

    @property
    def data_roots(self) -> list[DataRoot]:
        return self._core.data_roots

    @property
    def templates(self) -> list[TemplateInfo]:
        return self._core.catalog.list_templates()

    # ==================== Discovery ====================

    def list_sessions(self) -> list[SessionListing]:
        """List all sessions from the catalog."""
        try:
            return self._core.catalog.list_sessions()
        except Exception:
            log.exception("Failed to list sessions")
            return []

    # ==================== Session Lifecycle ====================

    async def create_session(
        self,
        template: str,
        *,
        data_root_name: str | None = None,
        name: str = "",
        description: str = "",
        collection: str = "",
    ) -> None:
        """Create a new session from a template."""
        if self._core.has_session:
            raise RuntimeError("A session is already active. Close it first.")

        self._set_phase("launching")

        try:
            await self._core.create_session(
                template=template,
                data_root_name=data_root_name,
                name=name,
                description=description,
                collection=collection,
            )
            log.info("Session created: %s", self._core.session.config.info.uid)  # type: ignore[union-attr]
            await self._wire_session()
        except Exception as e:
            log.exception("Failed to create session")
            self._set_phase("idle")
            self._set_error(f"Failed to create session: {e}")
            raise

    async def fork_session(
        self,
        source_session: str,
        *,
        data_root_name: str | None = None,
        name: str = "",
        description: str = "",
        collection: str = "",
        clear_stacks: bool = False,
    ) -> None:
        """Fork a new session from an existing one."""
        if self._core.has_session:
            raise RuntimeError("A session is already active. Close it first.")

        self._set_phase("launching")

        try:
            await self._core.create_session(
                source_session=source_session,
                data_root_name=data_root_name,
                name=name,
                description=description,
                collection=collection,
                clear_stacks=clear_stacks,
            )
            log.info("Session forked: %s", self._core.session.config.info.uid)  # type: ignore[union-attr]
            await self._wire_session()
        except Exception as e:
            log.exception("Failed to fork session")
            self._set_phase("idle")
            self._set_error(f"Failed to fork session: {e}")
            raise

    async def resume_session(self, uid: str) -> None:
        """Resume an existing session by UID."""
        if self._core.has_session:
            raise RuntimeError("A session is already active. Close it first.")

        self._set_phase("launching")

        try:
            await self._core.resume_session(uid)
            log.info("Session resumed: %s", uid)
            await self._wire_session()
        except Exception as e:
            log.exception("Failed to resume session")
            self._set_phase("idle")
            self._set_error(f"Failed to resume session: {e}")
            raise

    async def _wire_session(self) -> None:
        """Wire up stores and signals after session create/resume."""
        session = self._core.session
        if session is None:
            raise RuntimeError("No session to wire")

        await self.devices.start(session)
        log.info("DevicesStore started")

        # Bind stage store to axis adapters
        stage_cfg = session.microscope.config.stage
        x_adapter = self.devices.get_adapter(stage_cfg.x)
        y_adapter = self.devices.get_adapter(stage_cfg.y)
        z_adapter = self.devices.get_adapter(stage_cfg.z)
        if x_adapter and y_adapter and z_adapter:
            self.stage.bind(x_adapter, y_adapter, z_adapter)
            log.info("StageStore bound")

        self.devices_ready.emit()

        await self.grid.bind_session(session)
        log.info("GridStore bound to session")

        self._set_phase("ready")
        self.session_changed.emit(session)

    async def close_session(self) -> None:
        """Close the current session."""
        if not self._core.has_session:
            raise RuntimeError("No active session to close")

        try:
            await self.devices.stop()
            self.preview.reset()
            self.grid.unbind_session()
            self.stage.unbind()

            await self._core.close_session()
            log.info("Session closed")

        except Exception as e:
            log.exception("Error during session close")
            self._set_error(f"Error closing session: {e}")
        finally:
            self._set_phase("idle")
            self.session_changed.emit(None)

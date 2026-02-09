"""Voxel application coordinator.

This module provides the central application object for Voxel, managing:
- System configuration (from ~/.voxel/system.yaml)
- Session lifecycle (launch/close)
- Rig state access
- Child stores (devices, preview)

Uses Qt signals for state change notifications, enabling reactive UI updates.
"""

import logging
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QObject, Signal

from vxl import Session
from vxl.system import SessionDirectory, SessionRoot, SystemConfig, get_rig_path, list_rigs
from vxl_qt.store import DevicesStore, GridStore, PreviewStore, StageStore

if TYPE_CHECKING:
    from pathlib import Path

    from vxl import VoxelRig

log = logging.getLogger(__name__)

AppPhase = Literal["idle", "launching", "ready"]


class VoxelApp(QObject):
    """Central application coordinator with Qt signals.

    This class manages:
    - System configuration (session roots, available rigs)
    - Session lifecycle (launch, close)
    - Phase transitions (idle -> launching -> ready)
    - Child stores (devices, preview)

    Signals are emitted on state changes, allowing UI components to react.

    Usage:
        app = VoxelApp()

        # Connect to signals
        app.phase_changed.connect(on_phase_changed)
        app.session_changed.connect(on_session_ready)

        # Launch a session
        await app.launch_session("playground", "test-session", "simulated.local")

        # Access devices
        laser = app.devices.get_adapter("laser_488")

        # Access preview state
        histogram = app.preview.get_histogram("488")
    """

    phase_changed = Signal(str)  # AppPhase: 'idle' | 'launching' | 'ready'
    session_changed = Signal(object)  # Session instance or None
    error_changed = Signal(str)  # Error message
    devices_ready = Signal()  # Emitted when DevicesStore is started

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._phase: AppPhase = "idle"
        self._session: Session | None = None
        self._error: str = ""
        self._system_config: SystemConfig | None = None

        # Child stores
        self.devices = DevicesStore(parent=self)
        self.preview = PreviewStore(parent=self)
        self.grid = GridStore(parent=self)
        self.stage = StageStore(parent=self)

        self._load_system_config()

    def _load_system_config(self) -> None:
        """Load system configuration from ~/.voxel/system.yaml."""
        try:
            self._system_config = SystemConfig.load()
            log.info("Loaded system config with %d session roots", len(self._system_config.session_roots))
        except Exception as e:
            log.exception("Failed to load system config")
            self._set_error(f"Failed to load system config: {e}")

    def _set_phase(self, phase: AppPhase) -> None:
        """Set the application phase and emit signal."""
        if self._phase != phase:
            self._phase = phase
            log.debug("Phase changed: %s", phase)
            self.phase_changed.emit(phase)

    def _set_error(self, error: str) -> None:
        """Set the error message and emit signal."""
        self._error = error
        self.error_changed.emit(error)

    @property
    def phase(self) -> AppPhase:
        """Current application phase."""
        return self._phase

    @property
    def session(self) -> Session | None:
        """Active session, or None if no session is active."""
        return self._session

    @property
    def rig(self) -> "VoxelRig | None":
        """Active rig (via session.rig), or None if no session."""
        if self._session is None:
            return None
        return self._session.rig

    @property
    def error(self) -> str:
        """Current error message, or empty string if no error."""
        return self._error

    @property
    def system_config(self) -> SystemConfig | None:
        """System configuration from ~/.voxel/system.yaml."""
        return self._system_config

    @property
    def session_roots(self) -> list[SessionRoot]:
        """Available session roots."""
        if self._system_config is None:
            return []
        return self._system_config.session_roots

    @property
    def available_rigs(self) -> list[str]:
        """Available rig configurations from ~/.voxel/rigs/."""
        return list_rigs()

    def list_sessions(self, root_name: str) -> list[SessionDirectory]:
        """List sessions in a specific root.

        Args:
            root_name: Name of the session root

        Returns:
            List of SessionDirectory objects, sorted by modified time (newest first)
        """
        if self._system_config is None:
            return []
        try:
            return self._system_config.list_sessions(root_name)
        except Exception:
            log.exception("Failed to list sessions for root '%s'", root_name)
            return []

    def list_all_sessions(self) -> list[SessionDirectory]:
        """List sessions from all roots, sorted by modified time.

        Returns:
            List of SessionDirectory objects from all roots
        """
        all_sessions: list[SessionDirectory] = []
        for root in self.session_roots:
            all_sessions.extend(self.list_sessions(root.name))
        all_sessions.sort(key=lambda s: s.modified, reverse=True)
        return all_sessions

    async def launch_session(
        self,
        root_name: str,
        session_name: str,
        rig_config: str | None = None,
    ) -> None:
        """Launch a new session or resume an existing one.

        Args:
            root_name: Name of the session root
            session_name: Name of the session (folder name)
            rig_config: Rig config name (required for new sessions, ignored for existing)

        Raises:
            RuntimeError: If a session is already active
            ValueError: If root or rig config not found
        """
        if self._session is not None:
            raise RuntimeError("A session is already active. Close it first.")

        if self._system_config is None:
            raise RuntimeError("System config not loaded")

        root = self._system_config.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")

        session_dir = root.session_path(session_name)

        config_path: Path | None = None
        if rig_config:
            config_path = get_rig_path(rig_config)
            if config_path is None:
                raise ValueError(f"Rig config '{rig_config}' not found in ~/.voxel/rigs/")

        session_file = session_dir / "session.voxel.yaml"
        if session_file.exists():
            log.info("Resuming existing session: %s", session_dir)
            config_path = None
        else:
            if config_path is None:
                raise ValueError("Rig config required for new session")
            log.info("Creating new session: %s", session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)

        self._set_phase("launching")

        try:
            self._session = await Session.launch(session_dir, config_path)
            log.info("Session launched: %s", session_dir)

            await self.devices.start(self._session)
            log.info("DevicesStore started")

            # Bind stage store to axis adapters
            stage_cfg = self._session.rig.config.stage
            x_adapter = self.devices.get_adapter(stage_cfg.x)
            y_adapter = self.devices.get_adapter(stage_cfg.y)
            z_adapter = self.devices.get_adapter(stage_cfg.z)
            if x_adapter and y_adapter and z_adapter:
                self.stage.bind(x_adapter, y_adapter, z_adapter)
                log.info("StageStore bound")

            self.devices_ready.emit()

            await self.grid.bind_session(self._session)
            log.info("GridStore bound to session")

            self._set_phase("ready")
            self.session_changed.emit(self._session)

        except Exception as e:
            log.exception("Failed to launch session")
            self._session = None
            self._set_phase("idle")
            self._set_error(f"Failed to launch session: {e}")
            raise

    async def close_session(self) -> None:
        """Close the current session.

        Raises:
            RuntimeError: If no session is active
        """
        if self._session is None:
            raise RuntimeError("No active session to close")

        try:
            await self.devices.stop()
            self.preview.reset()
            self.grid.unbind_session()
            self.stage.unbind()

            if self._session.rig.preview.is_active:
                await self._session.rig.stop_preview()

            await self._session.rig.stop()
            log.info("Session closed: %s", self._session.session_dir)

        except Exception as e:
            log.exception("Error during session close")
            self._set_error(f"Error closing session: {e}")
        finally:
            self._session = None
            self._set_phase("idle")
            self.session_changed.emit(None)

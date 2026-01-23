"""Voxel Qt application state manager.

This module provides the central application state for Voxel Qt, managing:
- System configuration (from ~/.voxel/system.yaml)
- Session lifecycle (launch/close)
- Rig state access
- Device management

Uses Qt signals for state change notifications, enabling reactive UI updates.
"""

import logging
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QObject, Signal

# Reuse system config from voxel-studio (shares ~/.voxel/ directory)
from voxel_studio.system import (
    SessionDirectory,
    SessionRoot,
    SystemConfig,
    get_rig_path,
    list_rigs,
)

from voxel import Session
from voxel_qt.devices import DevicesManager

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

AppPhase = Literal["idle", "launching", "ready"]


class VoxelQtApp(QObject):
    """Central application state manager with Qt signals.

    This class manages:
    - System configuration (session roots, available rigs)
    - Session lifecycle (launch, close)
    - Phase transitions (idle -> launching -> ready)
    - Device adapters (via DevicesManager)

    Signals are emitted on state changes, allowing UI components to react.

    Usage:
        app = VoxelQtApp()

        # Connect to signals
        app.phase_changed.connect(on_phase_changed)
        app.session_launched.connect(on_session_ready)

        # Launch a session
        await app.launch_session("playground", "test-session", "simulated.local")

        # Access devices
        laser = app.devices.get_adapter("laser_488")
    """

    # Signals
    phase_changed = Signal(str)  # AppPhase: 'idle' | 'launching' | 'ready'
    session_launched = Signal(object)  # Session instance
    session_closed = Signal()
    error_occurred = Signal(str)  # Error message
    log_message = Signal(str, str)  # level, message
    devices_ready = Signal()  # DevicesManager started

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._phase: AppPhase = "idle"
        self._session: Session | None = None
        self._system_config: SystemConfig | None = None
        self._devices: DevicesManager | None = None

        # Load system config on init
        self._load_system_config()

    def _load_system_config(self) -> None:
        """Load system configuration from ~/.voxel/system.yaml."""
        try:
            self._system_config = SystemConfig.load()
            log.info(
                "Loaded system config with %d session roots",
                len(self._system_config.session_roots),
            )
        except Exception as e:
            log.exception("Failed to load system config")
            self.error_occurred.emit(f"Failed to load system config: {e}")

    # ==================== Properties ====================

    @property
    def phase(self) -> AppPhase:
        """Current application phase."""
        return self._phase

    @property
    def session(self) -> Session | None:
        """Active session, or None if no session is active."""
        return self._session

    @property
    def rig(self):
        """Active rig (via session.rig), or None if no session."""
        if self._session is None:
            return None
        return self._session.rig

    @property
    def devices(self) -> DevicesManager | None:
        """Device manager for accessing device adapters."""
        return self._devices

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

    # ==================== Session Management ====================

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
        # Sort by modified time (newest first)
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

        # Resolve session directory
        root = self._system_config.get_root(root_name)
        if root is None:
            raise ValueError(f"Session root '{root_name}' not found")

        session_dir = root.path / session_name

        # Resolve rig config path
        config_path: Path | None = None
        if rig_config:
            config_path = get_rig_path(rig_config)
            if config_path is None:
                raise ValueError(f"Rig config '{rig_config}' not found in ~/.voxel/rigs/")

        # Check if this is a new session or resume
        session_file = session_dir / "session.voxel.yaml"
        if session_file.exists():
            log.info("Resuming existing session: %s", session_dir)
            config_path = None  # Use existing config
        else:
            if config_path is None:
                raise ValueError("Rig config required for new session")
            log.info("Creating new session: %s", session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)

        # Set phase to launching
        self._set_phase("launching")

        try:
            # Launch the session
            self._session = await Session.launch(session_dir, config_path)
            log.info("Session launched: %s", session_dir)

            # Initialize device manager
            self._devices = DevicesManager(self._session, parent=self)
            await self._devices.start()
            log.info("DevicesManager started")
            self.devices_ready.emit()

            # Transition to ready
            self._set_phase("ready")
            self.session_launched.emit(self._session)

        except Exception as e:
            log.exception("Failed to launch session")
            self._session = None
            self._devices = None
            self._set_phase("idle")
            self.error_occurred.emit(f"Failed to launch session: {e}")
            raise

    async def close_session(self) -> None:
        """Close the current session.

        Raises:
            RuntimeError: If no session is active
        """
        if self._session is None:
            raise RuntimeError("No active session to close")

        try:
            # Stop device manager
            if self._devices:
                await self._devices.stop()
                self._devices = None

            # Stop preview if running
            if self._session.rig.preview.is_active:
                await self._session.rig.stop_preview()

            # Stop the rig
            await self._session.rig.stop()

            log.info("Session closed: %s", self._session.session_dir)

        except Exception as e:
            log.exception("Error during session close")
            self.error_occurred.emit(f"Error closing session: {e}")
        finally:
            self._session = None
            self._devices = None
            self._set_phase("idle")
            self.session_closed.emit()

    # ==================== Internal ====================

    def _set_phase(self, phase: AppPhase) -> None:
        """Set the application phase and emit signal."""
        if self._phase != phase:
            self._phase = phase
            log.debug("Phase changed: %s", phase)
            self.phase_changed.emit(phase)

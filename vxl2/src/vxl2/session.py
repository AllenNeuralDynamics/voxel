"""Session — top-level runtime for a user's imaging session.

Constructed with a loaded ``SessionStore``; Session pulls config from the store,
builds the rig from ``config.rig``, and composes controllers (preview,
acquisition, stacks). Owns the mode state machine, wires cross-controller
callbacks, and drives session-level lifecycle (rig + controllers + autosave).

Controllers are composed, not inherited. Each owns its domain:
 - ``rig.profiles`` (on the rig): active profile + device config + sync task + FOV
 - ``session.preview``: live preview activity
 - ``session.acquisition``: one-shot stack runs
 - ``session.stacks``: stack CRUD + plan ordering + FOV-driven resize

Session's job is **coordination**: mode gating, cross-controller wiring, and
passing the right config values into engines at the right moments.
"""

import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vxl2.camera.preview import PreviewViewport
from vxl2.config import SessionConfig
from vxl2.controllers import AcquisitionEngine, PreviewController, Stacks
from vxl2.metadata import resolve_metadata_class
from vxl2.microscope import Microscope
from vxl2.stack import StackResult
from vxl2.store import SessionStore

if TYPE_CHECKING:
    from vxlib import Unsub


class SessionMode(StrEnum):
    IDLE = "idle"
    PREVIEWING = "previewing"
    ACQUIRING = "acquiring"


class Session:
    """Top-level runtime for a user's imaging session.

    Takes a loaded ``SessionStore``; derives everything else from ``store.config``.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        self._config: SessionConfig = store.config
        self._microscope = Microscope(config=self._config)
        self._log = logging.getLogger(f"Session({self._config.info.uid})")

        # Controllers composed by Session. All take rig (and optionally config).
        self.preview = PreviewController(self._microscope)
        self.acquisition = AcquisitionEngine(self._microscope)
        self.stacks = Stacks(self._microscope, self._config)

        self._unsub_profile: Unsub | None = None

    # ==================== Lifecycle ====================

    async def open(self) -> None:
        """Open rig, controllers, wire callbacks, and begin autosaving."""
        await self._microscope.open()
        await self.stacks.open()
        self._unsub_profile = self._microscope.profiles.profile_changed.subscribe(self._on_profile_changed)
        # rig.profiles.open() fires profile_changed before we subscribe — apply
        # initial colormaps explicitly to cover that first activation.
        await self.preview.apply_default_colormaps(self._microscope.profiles.default_colormaps())
        await self._store.start_autosave()

    async def close(self) -> None:
        """Unwire callbacks, close controllers, flush autosave, close rig."""
        if self._unsub_profile is not None:
            self._unsub_profile()
            self._unsub_profile = None
        await self._store.stop_autosave()
        await self.stacks.close()
        await self._microscope.close()
        self._log.info("Session closed")

    # ==================== Properties ====================

    @property
    def microscope(self) -> Microscope:
        return self._microscope

    @property
    def mode(self) -> SessionMode:
        """Derived from controllers — no stored mode state."""
        if self.acquisition.is_running:
            return SessionMode.ACQUIRING
        if self.preview.is_running:
            return SessionMode.PREVIEWING
        return SessionMode.IDLE

    @property
    def config(self) -> SessionConfig:
        return self._config

    @property
    def store_path(self) -> Path:
        """Resolved base path for acquired zarrs.

        Prefers ``info.data_path`` (chosen at session creation) over
        ``output.store_path`` (user-editable default).
        """
        data_path = self._config.info.data_path
        return Path(data_path) if data_path else self._config.output.store_path

    @property
    def metadata(self) -> dict[str, Any]:
        return self._config.metadata

    @property
    def metadata_schema(self) -> str:
        return self._config.metadata_schema

    # ==================== Metadata ====================

    def set_metadata_schema(self, target: str) -> None:
        """Change the metadata schema class; resets values to the new schema's defaults.

        Blocked after any stack has been acquired — provenance fields would be
        invalidated by the schema switch.
        """
        if self.stacks.has_acquired:
            raise ValueError("Cannot change metadata schema after acquisition has started")
        cls = resolve_metadata_class(target)
        self._config.metadata_schema = target
        self._config.metadata = cls().model_dump()

    def update_metadata(self, values: dict[str, Any]) -> None:
        """Merge ``values`` into current metadata, validating against the active schema.

        After acquisition starts, only annotation fields (non-provenance) are editable.
        """
        cls = resolve_metadata_class(self._config.metadata_schema)
        if self.stacks.has_acquired:
            annotation_fields = cls.annotation_fields()
            for key in values:
                if key not in annotation_fields:
                    raise ValueError(f"Cannot modify provenance field '{key}' after acquisition has started")
        merged = {**self._config.metadata, **values}
        cls(**merged)  # validate — raises if invalid
        self._config.metadata = merged

    # ==================== Mode-gated actions ====================

    async def start_preview(self, crop: PreviewViewport | None = None) -> None:
        """Begin preview. Blocked if anything else is already running."""
        if self.acquisition.is_running:
            raise RuntimeError("Cannot start preview during acquisition")
        if self.preview.is_running:
            return
        await self.preview.start(crop)

    async def stop_preview(self) -> None:
        """Halt preview. No-op if not previewing."""
        if not self.preview.is_running:
            return
        await self.preview.stop()

    async def set_active_profile(self, profile_id: str) -> None:
        """Switch profiles, pausing/resuming preview around the switch."""
        if self.acquisition.is_running:
            raise RuntimeError("Cannot switch profiles during acquisition")
        restart = self.preview.is_running
        if restart:
            await self.stop_preview()
        await self._microscope.profiles.set_active_profile(profile_id)
        if restart:
            await self.start_preview()

    async def acquire_stack(self, stack_id: str) -> StackResult:
        """Run a single acquisition. Stops preview first if running."""
        if self.acquisition.is_running:
            raise RuntimeError("Another acquisition is in progress")
        if self.preview.is_running:
            await self.stop_preview()
        stack = self.stacks[stack_id]
        return await self.acquisition.run(
            stack,
            store_path=self.store_path,
            max_level=self._config.output.max_level,
            compression=self._config.output.compression,
        )

    async def acquire_all(self) -> list[StackResult]:
        """Acquire every PLANNED stack in traversal order."""
        results: list[StackResult] = []
        while (stack := self.stacks.next_planned()) is not None:
            results.append(await self.acquire_stack(stack.stack_id))
        return results

    async def update_waveforms(self, *, waveforms: dict | None = None, timing: dict | None = None) -> None:
        """Edit active profile's waveforms/timing and push to the DAQ. Blocked during acquisition."""
        if self.acquisition.is_running:
            raise RuntimeError("Cannot update waveforms while acquiring")
        await self._microscope.profiles.update_waveforms(waveforms=waveforms, timing=timing)

    # ==================== Private ====================

    async def _on_profile_changed(self, _profile_id: str) -> None:
        """Reapply default colormaps when the active profile changes."""
        await self.preview.apply_default_colormaps(self._microscope.profiles.default_colormaps())

"""SessionService — composition root for an active session.

Holds the class-bearing peers (Devices, Preview) that have shared state
across handlers. Classless domains (profile, acquisition, stacks) are wired
inline via private setup methods or have no session-time hooks at all.

Status broadcasts driven by ``profiles.fov`` / ``session.mode`` subscriptions
fan out via the ``notify_status`` callback supplied by AppService.
"""

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

from vxl import Session
from vxl.metadata import resolve_metadata_class
from vxl.stack import StackProgress
from vxl_web.protocol.device import DeviceSnapshot, DevicesSnapshot
from vxl_web.protocol.profile import ProfileSelection
from vxl_web.protocol.session import SessionDetails, SessionStateUpdate
from vxl_web.wire import ClientId, MsgBus

from ._devices import DevicesService
from ._preview import PreviewService

log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


async def snapshot_devices(session: Session) -> DevicesSnapshot:
    """Gather an on-demand snapshot of all devices with their interfaces.

    Used by both ``/session/devices`` REST and ``SessionService.get_session_details``.
    """
    devices: dict[str, DeviceSnapshot] = {}
    for device_id, handle in session.microscope.devices.items():
        try:
            iface = await handle.interface()
            devices[device_id] = DeviceSnapshot(id=device_id, connected=True, interface=iface)
        except Exception as e:
            log.warning("Failed to get interface for device '%s': %s", device_id, e)
            devices[device_id] = DeviceSnapshot(id=device_id, connected=False, error=str(e))
    return DevicesSnapshot(devices=devices, count=len(devices))


class SessionService:
    """Composition root for an active session."""

    def __init__(self, session: Session, bus: MsgBus, notify_status: Callable[[], Awaitable[None]]) -> None:
        self.session = session
        self.bus = bus
        self._notify_status = notify_status

        # Class-bearing peers (real shared state)
        self.devices = DevicesService(session, bus)
        self.preview = PreviewService(session, bus)

        # Inline lifecycle wiring for classless domains + status subscriptions.
        self._teardowns: list[Callable[[], None]] = [
            self._setup_profile(),
            self._setup_acquisition(),
            session.microscope.profiles.fov.subscribe(self._fire_status),
            session.mode.subscribe(self._fire_status),
        ]

    async def open(self) -> None:
        await self.devices.open()

    async def close(self) -> None:
        for t in self._teardowns:
            with suppress(Exception):
                t()
        self._teardowns.clear()
        for fn in (self.devices.close, self.preview.close):
            try:
                await fn()
            except Exception:
                log.exception("Error in %s", fn.__qualname__)

    async def stop_preview_for_idle(self) -> None:
        """Stop preview when the last WS client disconnects (bleaching safety)."""
        try:
            await self.session.stop_preview()
        except Exception:
            log.exception("Error stopping preview for idle")

    # ---- Aggregates ----

    async def get_session_details(self) -> SessionDetails:
        cls = resolve_metadata_class(self.session.metadata_schema)
        return SessionDetails(
            config=self.session.config.model_dump(mode="json"),
            metadata_schema=cls.model_json_schema(),
            devices=await snapshot_devices(self.session),
        )

    async def get_status(self) -> SessionStateUpdate:
        preview_configs = await self.preview.session.preview.get_channel_preview_configs()
        profiles = self.session.microscope.profiles
        return SessionStateUpdate(
            active_profile_id=profiles.active_id,
            mode=self.session.mode.value,
            preview=preview_configs,
            metadata=self.session.metadata,
            plan=self.session.config.plan.model_dump(mode="json"),
            output=self.session.config.output.model_dump(mode="json"),
            grid=self.session.config.grid.model_dump(mode="json"),
            stacks={s.stack_id: s.model_dump() for s in self.session.stacks},
            stack_order=self.session.stacks.compute_order(),
            fov=profiles.fov.value,
            timestamp=_utc_timestamp(),
        )

    # ---- Inline domain setup (classless peers) ----

    def _setup_profile(self) -> Callable[[], None]:
        """Wire ``profile.changed`` event + ``profile.update`` bus command."""

        async def on_profile_changed(profile_id: str) -> None:
            self.bus.broadcast("profile.changed", ProfileSelection(profile_id=profile_id))
            await self._notify_status()

        async def on_update(cmd: ProfileSelection, _sender_id: ClientId) -> None:
            await self.session.set_active_profile(cmd.profile_id)

        unsubs: list[Callable[[], None]] = [
            self.session.microscope.profiles.profile_changed.subscribe(on_profile_changed),
            self.bus.on_command("profile.update", ProfileSelection, on_update),
        ]

        def teardown() -> None:
            for u in unsubs:
                u()

        return teardown

    def _setup_acquisition(self) -> Callable[[], None]:
        """Forward ``session.acquisition.progress`` updates to ``acquisition.stack.progress``."""

        async def on_progress(progress: StackProgress | None) -> None:
            if progress is None:
                return
            self.bus.broadcast("acquisition.stack.progress", progress)

        return self.session.acquisition.progress.subscribe(on_progress)

    async def _fire_status(self, _value: object) -> None:
        await self._notify_status()


__all__ = ["DevicesService", "PreviewService", "SessionService", "snapshot_devices"]

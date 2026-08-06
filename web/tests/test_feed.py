from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from rigup.wire import pack, unpack
from vxl_web.feed import AppFeed, AppStatus, PreviewUpdate

from vxl.camera import PreviewViewport
from vxl.instrument.feed import InstrumentUpdate
from vxlib import Cell, Emitter


class _Bus:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[str, BaseModel, str | None, bool]] = []
        self.handlers: dict[str, Any] = {}

    def broadcast(
        self,
        topic: str,
        body: BaseModel,
        *,
        exclude: str | None = None,
        exclude_unset: bool = False,
    ) -> None:
        self.broadcasts.append((topic, body, exclude, exclude_unset))

    def on_command(self, topic: str, _schema: type[BaseModel], handler: Any) -> Any:
        self.handlers[topic] = handler

        def unsubscribe() -> None:
            self.handlers.pop(topic, None)

        return unsubscribe


class _OwnedFeed:
    def __init__(self) -> None:
        self.updates = Emitter[InstrumentUpdate]()


class _Instrument:
    def __init__(self, name: str) -> None:
        self.path = Path(f"{name}.voxel")
        self.feed = _OwnedFeed()
        self.viewports: list[PreviewViewport] = []

    def update_viewport(self, viewport: PreviewViewport) -> None:
        self.viewports.append(viewport)


class _App:
    def __init__(self) -> None:
        self.active = Cell[Any | None](None)


async def test_app_feed_follows_only_the_active_instrument() -> None:
    app = _App()
    bus = _Bus()
    bridge = AppFeed(cast("Any", app), cast("Any", bus))
    first = _Instrument("first")
    second = _Instrument("second")
    update = InstrumentUpdate(
        stream_id="stream",
        seq=1,
        observed_at_unix_us=10,
        active_acquisition=None,
    )

    bridge.attach()
    assert bus.broadcasts[-1][0:2] == ("app.status", AppStatus(active=None))

    await app.active.set(first)
    assert bus.broadcasts[-1][0:2] == ("app.status", AppStatus(active="first"))
    await first.feed.updates.emit(update)
    assert bus.broadcasts[-1] == ("instrument.update", update, None, True)

    await app.active.set(second)
    count = len(bus.broadcasts)
    await first.feed.updates.emit(update)
    assert len(bus.broadcasts) == count
    await second.feed.updates.emit(update)
    assert bus.broadcasts[-1] == ("instrument.update", update, None, True)

    viewport = PreviewViewport(x=0.1, y=0.2, w=0.5, h=0.5)
    await bus.handlers["preview.update"](PreviewUpdate(viewport=viewport), "client")
    assert second.viewports == [viewport]
    assert bus.broadcasts[-1][0:3] == ("preview.updates", PreviewUpdate(viewport=viewport), "client")

    bridge.detach()
    assert "preview.update" not in bus.handlers


def test_sparse_instrument_update_preserves_explicit_null() -> None:
    update = InstrumentUpdate(
        stream_id="stream",
        seq=1,
        observed_at_unix_us=10,
        active_acquisition=None,
    )

    assert unpack(pack(update, exclude_unset=True)) == {
        "stream_id": "stream",
        "seq": 1,
        "observed_at_unix_us": 10,
        "active_acquisition": None,
    }

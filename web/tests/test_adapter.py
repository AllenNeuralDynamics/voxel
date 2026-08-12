from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pydantic import BaseModel
from rigup.wire import pack, unpack
from vxl_web.adapter import AppStatus, PreviewUpdate, VoxelWebAdapter
from vxl_web.websocket import MsgBus

from vxl.instrument.feed import InstrumentUpdate
from vxl.preview import PreviewViewport
from vxlib import Cell, Emitter


class _OwnedFeed:
    def __init__(self) -> None:
        self.updates = Emitter[InstrumentUpdate]()
        self.frames = Emitter[Any]()
        self.delivery_stream_id = Cell("delivery")


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
        self.records = SimpleNamespace(logs=Emitter[Any]())


async def test_adapter_follows_only_the_active_instrument(monkeypatch: Any) -> None:
    broadcasts: list[tuple[str, BaseModel, str | None, bool]] = []
    handlers: dict[str, Any] = {}

    def broadcast(
        _bus: MsgBus,
        topic: str,
        body: BaseModel,
        *,
        exclude: str | None = None,
        exclude_unset: bool = False,
    ) -> None:
        broadcasts.append((topic, body, exclude, exclude_unset))

    def on_command(_bus: MsgBus, topic: str, _schema: type[BaseModel], handler: Any) -> Any:
        handlers[topic] = handler

        def unsubscribe() -> None:
            handlers.pop(topic, None)

        return unsubscribe

    monkeypatch.setattr(MsgBus, "broadcast", broadcast)
    monkeypatch.setattr(MsgBus, "on_command", on_command)

    app = _App()
    adapter = VoxelWebAdapter(cast("Any", app))
    first = _Instrument("first")
    second = _Instrument("second")
    update = InstrumentUpdate(
        stream_id="stream",
        seq=1,
        observed_at_unix_us=10,
        active_acquisition=None,
    )

    adapter.attach()
    assert broadcasts[-1][0:2] == ("app.status", AppStatus(active=None))

    await app.active.set(first)
    assert broadcasts[-1][0:2] == ("app.status", AppStatus(active="first"))
    await first.feed.updates.emit(update)
    assert broadcasts[-1] == ("instrument.feed.updates", update, None, True)

    await app.active.set(second)
    count = len(broadcasts)
    await first.feed.updates.emit(update)
    assert len(broadcasts) == count
    await second.feed.updates.emit(update)
    assert broadcasts[-1] == ("instrument.feed.updates", update, None, True)

    viewport = PreviewViewport(x=0.1, y=0.2, w=0.5, h=0.5)
    await handlers["instrument.preview"](PreviewUpdate(viewport=viewport), "client")
    assert second.viewports == [viewport]
    assert broadcasts[-1][0:3] == ("instrument.preview", PreviewUpdate(viewport=viewport), "client")

    await adapter.close()
    assert "instrument.preview" not in handlers


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

"""Instrument-owned, transport-neutral status and preview feeds.

The feed materializes the current instrument view from reactive state and pushed
device-property updates, and associates packed preview source frames with that
same status timeline.

The :class:`~vxl.instrument.core.Instrument` owns the feed and its lifecycle.
"""

import time
import uuid
from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rigup import DeviceInterface, DeviceProps, PropResults, Result
from vxl.preview.protocol import (
    PreviewEmission,
    PreviewFramePacket,
    PreviewLayer,
    PreviewSourceEmission,
    StreamCursor,
)
from vxlib import Cell, Emitter, ReactiveQuery, Readable, Subscribable, Teardown

from .models import AcquisitionMode, ActiveAcquisitionState, TaskTile
from .state import InstrumentDefaults, InstrumentState
from .topology import HALConfig

type DevicePropsUpdate = tuple[str, DeviceProps]
type UnixMicroseconds = int


def _unix_time_us() -> UnixMicroseconds:
    return time.time_ns() // 1_000


def _prop_results(props: DeviceProps) -> PropResults:
    return PropResults(results={name: Result.ok(model) for name, model in props.items()})


class DeviceSnapshot(BaseModel, frozen=True):
    """Legacy feed representation of one successfully inspected device."""

    id: str
    connected: bool
    interface: DeviceInterface | None = None
    error: str | None = None


class InstrumentCursor(BaseModel, frozen=True):
    """Position in one opened instrument's ordered feed."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)


class InstrumentRuntimeStatus(BaseModel, frozen=True):
    """Current dynamic instrument state, excluding device properties."""

    mode: AcquisitionMode
    active_profile_id: str
    delivery_stream_id: str
    fov: tuple[float, float] | None
    routing_targets: dict[str, str]
    state: InstrumentState
    task_tiles: list[TaskTile]


class InstrumentView(BaseModel, frozen=True):
    """Complete materialized view returned when a consumer connects or resynchronizes."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    generated_at_unix_us: UnixMicroseconds = Field(ge=0)
    status: InstrumentRuntimeStatus
    device_props: dict[str, PropResults]
    active_acquisition: ActiveAcquisitionState | None
    defaults: InstrumentDefaults
    hardware: HALConfig
    devices: dict[str, DeviceSnapshot]

    @property
    def cursor(self) -> InstrumentCursor:
        """Return the continuation cursor represented by this view."""
        return InstrumentCursor(stream_id=self.stream_id, seq=self.seq)


class InstrumentUpdate(BaseModel, frozen=True):
    """Partial materialized-view update.

    Missing sections are unchanged. An explicitly supplied ``None`` remains a
    meaningful value, notably when ``active_acquisition`` is cleared. Transport
    adapters must serialize this model with ``exclude_unset=True``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    _SECTIONS: ClassVar[frozenset[str]] = frozenset({"status", "device_props", "active_acquisition", "defaults"})

    stream_id: str = Field(min_length=1)
    seq: int = Field(gt=0)
    observed_at_unix_us: UnixMicroseconds = Field(ge=0)
    status: InstrumentRuntimeStatus | None = None
    device_props: dict[str, PropResults] | None = None
    active_acquisition: ActiveAcquisitionState | None = None
    defaults: InstrumentDefaults | None = None

    @model_validator(mode="after")
    def _require_section(self) -> Self:
        if not self.model_fields_set.intersection(self._SECTIONS):
            raise ValueError("an instrument update must set at least one state section")
        return self

    @property
    def cursor(self) -> InstrumentCursor:
        """Return the cursor assigned to this update."""
        return InstrumentCursor(stream_id=self.stream_id, seq=self.seq)

    def wire_dict(self) -> dict[str, Any]:
        """Serialize only explicitly populated sections, preserving explicit nulls."""
        return self.model_dump(mode="json", include=self.model_fields_set)


class InstrumentSource(Protocol):
    """Instrument surface required by :class:`InstrumentFeed`.

    ``Instrument`` satisfies this protocol; tests may use a hardware-free fake.
    """

    @property
    def state(self) -> Readable[InstrumentState]: ...

    @property
    def default(self) -> Readable[InstrumentDefaults]: ...

    @property
    def mode(self) -> Readable[AcquisitionMode]: ...

    @property
    def acquisition(self) -> Readable[ActiveAcquisitionState | None]: ...

    @property
    def active_profile_id(self) -> Readable[str]: ...

    @property
    def routing_targets(self) -> Readable[dict[str, str]]: ...

    @property
    def device_props(self) -> dict[str, DeviceProps]: ...

    @property
    def device_props_updates(self) -> Subscribable[DevicePropsUpdate]: ...

    @property
    def device_interfaces(self) -> Mapping[str, DeviceInterface]: ...

    @property
    def preview(self) -> Subscribable[PreviewSourceEmission]: ...

    @property
    def preview_revision(self) -> Readable[int]: ...

    @property
    def hardware_config(self) -> HALConfig: ...

    @property
    def fov(self) -> ReactiveQuery[tuple[float, float]]: ...

    @property
    def task_tiles(self) -> Readable[list[TaskTile]]: ...


class InstrumentFeed:
    """Materialized status and preview frame feed owned by one :class:`Instrument`.

    Construction is inert. :meth:`open` attaches subscriptions and snapshots
    the properties already materialized by the instrument; consumer connections
    subsequently use :meth:`view` without querying hardware. Preview frames use
    a separate delivery cursor while carrying the current status cursor in each
    VXPD packet.
    """

    def __init__(self, source: InstrumentSource) -> None:
        self._source = source
        self._updates = Emitter[InstrumentUpdate]()
        self._frames = Emitter[PreviewEmission]()
        self._unsubs: list[Teardown] = []
        self._stream_id: str | None = None
        self._seq = 0
        self._delivery_stream_id = Cell(uuid.uuid4().hex)
        self._delivery_seq = 0
        self._device_props: dict[str, PropResults] = {}
        self._devices: dict[str, DeviceSnapshot] = {}
        self._ready = False

    @property
    def updates(self) -> Subscribable[InstrumentUpdate]:
        """Ordered partial updates produced after the feed is opened."""
        return self._updates

    @property
    def frames(self) -> Subscribable[PreviewEmission]:
        """Delivered VXPD preview packets."""
        return self._frames

    @property
    def delivery_stream_id(self) -> Readable[str]:
        """Identity of the current preview delivery stream."""
        return self._delivery_stream_id

    @property
    def is_open(self) -> bool:
        """Whether the initial view is ready for consumers."""
        return self._ready

    @property
    def cursor(self) -> InstrumentCursor:
        """Return the latest assigned cursor."""
        return InstrumentCursor(stream_id=self._require_stream_id(), seq=self._seq)

    async def open(self) -> None:
        """Start a new feed lifetime from the instrument's materialized state."""
        if self._stream_id is not None:
            raise RuntimeError("instrument feed is already open")

        self._stream_id = uuid.uuid4().hex
        self._seq = 0
        self._device_props = {}
        self._devices = {}
        self._ready = False
        self._attach()

        try:
            self._devices = {
                device_id: DeviceSnapshot(id=device_id, connected=True, interface=interface)
                for device_id, interface in self._source.device_interfaces.items()
            }
            self._device_props = {
                device_id: _prop_results(props) for device_id, props in self._source.device_props.items()
            }
        except BaseException:
            self.close()
            raise
        self._ready = True

    def close(self) -> None:
        """Detach subscriptions and discard this feed lifetime. Idempotent."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self._stream_id = None
        self._seq = 0
        self._device_props = {}
        self._devices = {}
        self._ready = False

    def view(self) -> InstrumentView:
        """Return a complete cached view without performing device I/O."""
        if not self._ready:
            raise RuntimeError("instrument feed is not open")
        return InstrumentView(
            stream_id=self._require_stream_id(),
            seq=self._seq,
            generated_at_unix_us=_unix_time_us(),
            status=self._status(),
            device_props=dict(self._device_props),
            active_acquisition=self._source.acquisition.value,
            defaults=self._source.default.value,
            hardware=self._source.hardware_config,
            devices=dict(self._devices),
        )

    async def reset_preview(self) -> None:
        """Begin a new preview delivery stream and reset its frame sequence."""
        self._delivery_seq = 0
        await self._delivery_stream_id.set(uuid.uuid4().hex)

    async def deliver_preview(self, channel_id: str, layer: PreviewLayer, frame: bytes) -> None:
        """Wrap one packed VXPS source frame and emit the resulting VXPD packet."""
        status_cursor = self.cursor
        delivery_seq = self._delivery_seq
        packet = PreviewFramePacket.wrap(
            frame,
            channel_id=channel_id,
            delivery_cursor=StreamCursor(stream_id=self._delivery_stream_id.value, seq=delivery_seq),
            state_cursor=StreamCursor(stream_id=status_cursor.stream_id, seq=status_cursor.seq),
            stamped_at_unix_us=_unix_time_us(),
        ).pack()
        self._delivery_seq = delivery_seq + 1
        await self._frames.emit((channel_id, layer, packet))

    def _attach(self) -> None:
        source = self._source
        self._unsubs = [
            source.state.subscribe(self._on_status),
            source.mode.subscribe(self._on_status),
            source.active_profile_id.subscribe(self._on_status),
            self._delivery_stream_id.subscribe(self._on_status),
            source.task_tiles.subscribe(self._on_status),
            source.fov.subscribe(self._on_status),
            source.routing_targets.subscribe(self._on_status),
            source.acquisition.subscribe(self._on_acquisition),
            source.default.subscribe(self._on_defaults),
            source.device_props_updates.subscribe(self._on_device_props),
            source.preview.subscribe(self._on_preview),
            source.preview_revision.subscribe(self._on_preview_revision),
        ]

    async def _on_status(self, _value: object) -> None:
        if self._stream_id is None:
            return
        await self._emit(status=self._status())

    async def _on_acquisition(self, acquisition: ActiveAcquisitionState | None) -> None:
        if self._stream_id is None:
            return
        await self._emit(active_acquisition=acquisition)

    async def _on_defaults(self, defaults: InstrumentDefaults) -> None:
        if self._stream_id is None:
            return
        await self._emit(defaults=defaults)

    async def _on_device_props(self, update: DevicePropsUpdate) -> None:
        if self._stream_id is None:
            return
        device_id, properties = update
        seq = self._next_seq()
        prop_results = _prop_results(properties)
        self._device_props[device_id] = prop_results
        await self._updates.emit(
            InstrumentUpdate(
                stream_id=self._stream_id,
                seq=seq,
                observed_at_unix_us=_unix_time_us(),
                device_props={device_id: prop_results},
            )
        )

    async def _on_preview(self, emission: PreviewSourceEmission) -> None:
        if self._stream_id is None:
            return
        channel_id, layer, frame = emission
        await self.deliver_preview(channel_id, layer, frame)

    async def _on_preview_revision(self, _revision: int) -> None:
        if self._stream_id is None:
            return
        await self.reset_preview()

    async def _emit(self, **sections: Any) -> None:
        stream_id = self._require_stream_id()
        seq = self._next_seq()
        await self._updates.emit(
            InstrumentUpdate(
                stream_id=stream_id,
                seq=seq,
                observed_at_unix_us=_unix_time_us(),
                **sections,
            )
        )

    def _status(self) -> InstrumentRuntimeStatus:
        source = self._source
        return InstrumentRuntimeStatus(
            mode=source.mode.value,
            active_profile_id=source.active_profile_id.value,
            delivery_stream_id=self._delivery_stream_id.value,
            fov=source.fov.cache,
            routing_targets=source.routing_targets.value,
            state=source.state.value,
            task_tiles=source.task_tiles.value,
        )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _require_stream_id(self) -> str:
        if self._stream_id is None:
            raise RuntimeError("instrument feed is not open")
        return self._stream_id

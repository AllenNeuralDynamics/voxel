"""Instrument-owned, transport-neutral state feed.

The feed materializes the current instrument view from reactive instrument state
and pushed device-property updates, assigns one ordered cursor to changes, and
exposes that same view and update stream to web and preview-service transport
adapters.

The :class:`~vxl.instrument.core.Instrument` owns the feed and its lifecycle.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Collection
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rigup import PropResults
from vxlib import Emitter, ReactiveQuery, Readable, Subscribable, Teardown

from .models import AcquisitionMode, ActiveAcquisitionState, DeviceSnapshot, TaskTile
from .state import InstrumentDefaults, InstrumentState
from .topology import HALConfig

log = logging.getLogger(__name__)

type DevicePropertyUpdate = tuple[str, PropResults]
type UnixMicroseconds = int


def _unix_time_us() -> UnixMicroseconds:
    return time.time_ns() // 1_000


class InstrumentCursor(BaseModel, frozen=True):
    """Position in one opened instrument's ordered feed."""

    stream_id: str = Field(min_length=1)
    seq: int = Field(ge=0)


class InstrumentStatus(BaseModel, frozen=True):
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
    status: InstrumentStatus
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
    status: InstrumentStatus | None = None
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
        return self.model_dump(mode="json", exclude_unset=True)


class InstrumentFeedSource(Protocol):
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
    def delivery_stream_id(self) -> Readable[str]: ...

    @property
    def routing_targets(self) -> Readable[dict[str, str]]: ...

    @property
    def device_property_updates(self) -> Subscribable[DevicePropertyUpdate]: ...

    @property
    def hardware_config(self) -> HALConfig: ...

    @property
    def fov(self) -> ReactiveQuery[tuple[float, float]]: ...

    @property
    def task_tiles(self) -> Readable[list[TaskTile]]: ...

    async def inspect_devices(self) -> dict[str, DeviceSnapshot]: ...

    async def get_device_properties(self, device_id: str, names: Collection[str] | None = None) -> PropResults: ...


class InstrumentFeed:
    """Materialized, sequenced read feed owned by one :class:`Instrument`.

    Construction is inert. :meth:`open` attaches subscriptions and primes the
    property cache once; consumer connections subsequently use :meth:`view`
    without querying hardware. :meth:`close` detaches every subscription.
    """

    def __init__(
        self,
        source: InstrumentFeedSource,
        *,
        clock: Callable[[], UnixMicroseconds] = _unix_time_us,
        stream_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._source = source
        self._clock = clock
        self._stream_id_factory = stream_id_factory
        self._updates = Emitter[InstrumentUpdate]()
        self._unsubs: list[Teardown] = []
        self._stream_id: str | None = None
        self._seq = 0
        self._device_props: dict[str, PropResults] = {}
        self._devices: dict[str, DeviceSnapshot] = {}
        self._prop_versions: dict[tuple[str, str], int] = {}
        self._ready = False

    @property
    def updates(self) -> Subscribable[InstrumentUpdate]:
        """Ordered partial updates produced after the feed is opened."""
        return self._updates

    @property
    def is_open(self) -> bool:
        """Whether the initial view is ready for consumers."""
        return self._ready

    @property
    def cursor(self) -> InstrumentCursor:
        """Return the latest assigned cursor."""
        return InstrumentCursor(stream_id=self._require_stream_id(), seq=self._seq)

    async def open(self) -> None:
        """Start a new feed lifetime and prime every connected device once."""
        if self._stream_id is not None:
            raise RuntimeError("instrument feed is already open")

        self._stream_id = self._stream_id_factory()
        self._seq = 0
        self._device_props = {}
        self._devices = {}
        self._prop_versions = {}
        self._ready = False
        self._attach()

        try:
            await self._prime_devices()
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
        self._prop_versions = {}
        self._ready = False

    def view(self) -> InstrumentView:
        """Return a complete cached view without performing device I/O."""
        if not self._ready:
            raise RuntimeError("instrument feed is not open")
        return InstrumentView(
            stream_id=self._require_stream_id(),
            seq=self._seq,
            generated_at_unix_us=self._clock(),
            status=self._status(),
            device_props=dict(self._device_props),
            active_acquisition=self._source.acquisition.value,
            defaults=self._source.default.value,
            hardware=self._source.hardware_config,
            devices=dict(self._devices),
        )

    def _attach(self) -> None:
        source = self._source
        self._unsubs = [
            source.state.subscribe(self._on_status),
            source.mode.subscribe(self._on_status),
            source.active_profile_id.subscribe(self._on_status),
            source.delivery_stream_id.subscribe(self._on_status),
            source.task_tiles.subscribe(self._on_status),
            source.fov.subscribe(self._on_status),
            source.routing_targets.subscribe(self._on_status),
            source.acquisition.subscribe(self._on_acquisition),
            source.default.subscribe(self._on_defaults),
            source.device_property_updates.subscribe(self._on_device_props),
        ]

    async def _prime_devices(self) -> None:
        self._devices = await self._source.inspect_devices()
        connected = [device_id for device_id, snapshot in self._devices.items() if snapshot.connected]
        starts = dict.fromkeys(connected, self._seq)
        results = await asyncio.gather(
            *(self._source.get_device_properties(device_id) for device_id in connected),
            return_exceptions=True,
        )

        for device_id, result in zip(connected, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                log.warning("Could not prime properties for device %s: %s", device_id, result)
                continue
            self._merge_device_props(device_id, result, unless_newer_than=starts[device_id])

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

    async def _on_device_props(self, update: DevicePropertyUpdate) -> None:
        if self._stream_id is None:
            return
        device_id, properties = update
        seq = self._next_seq()
        self._merge_device_props(device_id, properties, version=seq)
        await self._updates.emit(
            InstrumentUpdate(
                stream_id=self._stream_id,
                seq=seq,
                observed_at_unix_us=self._clock(),
                device_props={device_id: properties},
            )
        )

    async def _emit(self, **sections: Any) -> None:
        stream_id = self._require_stream_id()
        seq = self._next_seq()
        await self._updates.emit(
            InstrumentUpdate(
                stream_id=stream_id,
                seq=seq,
                observed_at_unix_us=self._clock(),
                **sections,
            )
        )

    def _status(self) -> InstrumentStatus:
        source = self._source
        return InstrumentStatus(
            mode=source.mode.value,
            active_profile_id=source.active_profile_id.value,
            delivery_stream_id=source.delivery_stream_id.value,
            fov=source.fov.cache,
            routing_targets=source.routing_targets.value,
            state=source.state.value,
            task_tiles=source.task_tiles.value,
        )

    def _merge_device_props(
        self,
        device_id: str,
        properties: PropResults,
        *,
        version: int | None = None,
        unless_newer_than: int | None = None,
    ) -> None:
        current = self._device_props.get(device_id)
        merged = dict(current.results) if current is not None else {}
        for name, result in properties.results.items():
            key = (device_id, name)
            if unless_newer_than is not None and self._prop_versions.get(key, -1) > unless_newer_than:
                continue
            merged[name] = result
            if version is not None:
                self._prop_versions[key] = version
        self._device_props[device_id] = PropResults(results=merged)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _require_stream_id(self) -> str:
        if self._stream_id is None:
            raise RuntimeError("instrument feed is not open")
        return self._stream_id

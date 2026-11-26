"""The station as feed topics: its view, its live frames, its newest acquisition, and its newest log line."""

from collections.abc import Mapping
from functools import reduce
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, JsonValue

from vxl.instrument.base import KeyedTopics
from vxl.live import LiveSourceEmission
from vxl.records import Acquisition, LogEntry, Records
from vxl.station.config import StationInfo
from vxl.station.station import StationStatus, StationView
from vxl.web.feed import FeedPublisher

if TYPE_CHECKING:
    from vxlib.lifecycle import Teardown
    from vxlib.reactivity import Readable, Subscribable

_MISSING = object()

_SPLIT_BY_FIELD = ("state", "default_state")
"""The fields of the instrument view that are 1 topic for each of their own fields."""


class StationTopics:
    """Publishes a station as topics: what changed in its view, each live frame under its camera and layer, the
    newest acquisition, and the newest log line. The newest acquisition is the one created last: a save of an older
    one, such as an unfinished run ended as interrupted at startup, does not replace it. A change of session
    publishes every topic again as 1 full message. The caller closes the publisher."""

    def __init__(
        self,
        info: StationInfo,
        view: "Readable[StationView]",
        live: "Subscribable[LiveSourceEmission]",
        records: Records,
        publisher: FeedPublisher,
    ) -> None:
        self._info = info
        self._publisher = publisher
        self._view = view.value
        self._parts = self._view_parts(info, self._view)
        self._records = records
        self._shown: Acquisition | None = None
        self._acquisition: dict[str, JsonValue] = {}
        self._log: dict[str, JsonValue] = {}
        publisher.replace(self._as_json(info, self._view, self._parts))
        self._teardowns: list[Teardown] = [
            view.subscribe(self._on_view),
            live.subscribe(self._on_frame),
            records.acquisitions.subscribe(self._on_acquisition),
            records.logs.subscribe(self._on_log),
        ]

    @classmethod
    def view_topics(cls, info: StationInfo, view: StationView) -> dict[str, JsonValue]:
        """Every topic of a station view, with its value as JSON. A topic is a field of the view. The instrument's
        states are split by field, and their profiles by id. A device is 1 topic for its interface and 1 for each
        property. A field of the instrument view marked with :class:`KeyedTopics` is 1 topic for each key. A field
        that is ``None`` has no topic."""
        return cls._as_json(info, view, cls._view_parts(info, view))

    def close(self) -> None:
        """Stop publishing."""
        for teardown in self._teardowns:
            teardown()
        self._teardowns = []

    def _on_view(self, view: StationView) -> None:
        before, self._view = self._view, view
        last, self._parts = self._parts, self._view_parts(self._info, view)
        if (before.session and before.session.info.id) != (view.session and view.session.info.id):
            self._publisher.replace({**self._as_json(self._info, view, self._parts), **self._acquisition, **self._log})
        else:
            self._publisher.publish(self._as_json(self._info, view, self._changes(last, self._parts)))

    def _on_frame(self, emission: LiveSourceEmission) -> None:
        camera, layer, frame, position = emission
        if self._view.status is StationStatus.ACTIVE:
            self._publisher.publish_frame(f"instrument.frames.{camera}.{layer}", frame, position)

    async def show_newest(self) -> None:
        """Publish the newest stored acquisition, as if it had just been saved. The topics start with none, since
        the store tells only of saves."""
        if (newest := await self._records.acquisitions.newest()) is not None:
            self._on_acquisition(newest)

    def _on_acquisition(self, acquisition: Acquisition) -> None:
        shown = self._shown
        if shown is not None and acquisition.id != shown.id and acquisition.created_at < shown.created_at:
            return
        self._shown = acquisition
        last, self._acquisition = self._acquisition, self._acquisition_topics(acquisition)
        self._publisher.publish(self._changes(last, self._acquisition))

    def _on_log(self, entry: LogEntry) -> None:
        self._log = {"log": entry.model_dump(mode="json")}
        self._publisher.publish(self._log)

    @staticmethod
    def _view_parts(info: StationInfo, view: StationView) -> dict[str, object]:
        """Each topic of the view with the object that it shows. An unchanged part of the view is the same object as
        before, so 2 results compare fast."""
        parts: dict[str, object] = {"station": info, "status": view.status, "error": view.error}
        if view.session is not None:
            parts["session"] = view.session.info
            for name, value in view.session.instrument:
                if name in _SPLIT_BY_FIELD:
                    for field, part in value:
                        if field == "profiles":
                            parts.update({f"instrument.{name}.profiles.{key}": item for key, item in part.items()})
                        else:
                            parts[f"instrument.{name}.{field}"] = part
                elif name == "devices":
                    for device_id, device in value.items():
                        topic = f"instrument.devices.{device_id}"
                        parts[f"{topic}.interface"] = device.interface
                        parts.update({f"{topic}.props.{prop}": item for prop, item in device.props.items()})
                elif StationTopics._keyed(type(view.session.instrument), name):
                    parts.update({f"instrument.{name}.{key}": item for key, item in value.items()})
                else:
                    parts[f"instrument.{name}"] = value
        return {topic: part for topic, part in parts.items() if part is not None}

    @staticmethod
    def _keyed(view_cls: type[BaseModel], name: str) -> bool:
        """Whether field ``name`` of the instrument view is marked with :class:`KeyedTopics`."""
        return any(isinstance(mark, KeyedTopics) for mark in view_cls.model_fields[name].metadata)

    @staticmethod
    def _changes[T](last: Mapping[str, T], now: Mapping[str, T]) -> dict[str, T | None]:
        """The topics of ``now`` whose value differs from ``last``, and ``None`` for each topic that is gone."""
        changed = {
            topic: value
            for topic, value in now.items()
            if (old := last.get(topic, _MISSING)) is not value and old != value
        }
        return {**changed, **dict.fromkeys(last.keys() - now.keys())}

    @classmethod
    def _as_json(cls, info: StationInfo, view: StationView, parts: Mapping[str, object]) -> dict[str, JsonValue]:
        """The value of each of ``parts`` as JSON, written by the view's own serializer: after ``instrument.``, a
        topic's name is its path in the instrument view."""
        topics: dict[str, JsonValue] = {}
        for topic, part in parts.items():
            if part is None:
                topics[topic] = None
            elif topic == "station":
                topics[topic] = info.model_dump(mode="json")
            elif topic == "session":
                topics[topic] = cls._dump(view, "session", "info")
            elif topic.startswith("instrument."):
                topics[topic] = cls._dump(view, "session", "instrument", *topic.split(".")[1:])
            else:
                topics[topic] = cls._dump(view, topic)
        return topics

    @staticmethod
    def _dump(view: StationView, *path: str) -> JsonValue:
        include = reduce(lambda inner, name: {name: inner}, reversed(path), cast("Any", True))
        value: Any = view.model_dump(mode="json", include=include)
        for name in path:
            value = value[name]
        return value

    @staticmethod
    def _acquisition_topics(acquisition: Acquisition) -> dict[str, JsonValue]:
        """An acquisition as topics, in the form of ``acquisition.json``: 1 topic for each field, and 1 for each
        visit."""
        fields = acquisition.for_readers()
        visits = fields.pop("visits")
        return {
            **{f"acquisition.{field}": value for field, value in fields.items() if value is not None},
            **{f"acquisition.visits.{index}": visit for index, visit in enumerate(visits)},
        }


__all__ = ["StationTopics"]

"""The schema of a rig file."""

from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    PositiveFloat,
    SerializationInfo,
    model_validator,
)
from vxlib.issues import KeyPath, Problems
from vxlib.schema import identifier

from .build import BuildConfig, dependencies, import_class
from .component import Part
from .interface import StreamTier

NodeKind = Literal["subprocess", "remote"]
ComponentUid = Annotated[str, identifier("Component UID")]
NodeId = Annotated[str, identifier("Node id")]


class DeviceConfig(BuildConfig):
    """How 1 device of the rig is built.

    ``streaming`` overrides the seconds between sends for the stream tiers it names. ``details`` holds information for
    people; the device does not get it.
    """

    streaming: dict[StreamTier, PositiveFloat] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


def _read_part(data: Any) -> Part:
    if isinstance(data, Part):
        return data
    if not isinstance(data, dict):
        raise ValueError("a part is written as its fields")
    fields = dict(data)
    target = fields.pop("target", None)
    cls = Part if target is None else import_class(str(target), Part)
    return cls.model_validate(fields)


def _write_part(part: Part, info: SerializationInfo) -> dict[str, Any]:
    data = part.model_dump(mode=info.mode, exclude={"uid"}, exclude_defaults=True)
    if type(part) is Part:
        return data
    return {"target": f"{type(part).__module__}.{type(part).__qualname__}", **data}


def _with_uids(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    entries: dict[Any, Any] = {}
    for uid, entry in data.items():
        if isinstance(entry, Part) and entry.uid != uid:
            raise ValueError(f"the part '{entry.uid}' is under the key '{uid}'")
        entries[uid] = {**entry, "uid": uid} if isinstance(entry, dict) else entry
    return entries


Parts = Annotated[
    dict[ComponentUid, Annotated[Part, PlainValidator(_read_part), PlainSerializer(_write_part)]],
    BeforeValidator(_with_uids),
]
"""The parts of a rig by UID; an entry names its class in ``target`` when it is not ``Part``."""


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "*"}


def _is_local_address(address: str) -> bool:
    if address.startswith(("ipc://", "inproc://")):
        return True
    if not address.startswith("tcp://"):
        return False
    body = address[len("tcp://") :]
    if body.startswith("["):
        closing = body.find("]")
        host = body[1:closing] if closing != -1 else body
    elif ":" in body:
        host = body.rsplit(":", 1)[0]
    else:
        host = body
    return host in _LOCAL_HOSTS


class NodeConfig(BaseModel, frozen=True):
    """A process of the rig apart from the orchestrator's own, with the devices that run in it.

    A ``subprocess`` node is started by the rig on this host; a ``remote`` node is started elsewhere and reached at
    ``address``. When ``kind`` is omitted, a missing or local address means ``subprocess``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: NodeKind
    address: str | None = None
    devices: dict[ComponentUid, DeviceConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _infer_kind(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "kind" in data:
            return data
        address = data.get("address")
        if address is None or _is_local_address(str(address)):
            return {**data, "kind": "subprocess"}
        return {**data, "kind": "remote"}

    @model_validator(mode="after")
    def _check_address(self) -> Self:
        found = Problems()
        if self.kind == "remote" and self.address is None:
            found.add("remote_node_address", "remote node requires an address", "address")
        found.raise_if_any(type(self).__name__)
        return self


class RigConfig(BaseModel, frozen=True):
    """The parts of a rig, the devices of the orchestrator's own process, and the other processes."""

    model_config = ConfigDict(extra="forbid")

    parts: Parts = Field(default_factory=dict)
    devices: dict[ComponentUid, DeviceConfig] = Field(default_factory=dict)
    nodes: dict[NodeId, NodeConfig] = Field(default_factory=dict)

    @property
    def all_devices(self) -> dict[ComponentUid, DeviceConfig]:
        return {**self.devices, **{uid: config for node in self.nodes.values() for uid, config in node.devices.items()}}

    def component_location(self, uid: ComponentUid) -> KeyPath:
        """Return the key path of ``uid`` in the rig file, or raise ``KeyError``."""
        if uid in self.parts:
            return ("parts", uid)
        if uid in self.devices:
            return ("devices", uid)
        for node_id, node in self.nodes.items():
            if uid in node.devices:
                return ("nodes", node_id, "devices", uid)
        raise KeyError(uid)

    def _component_locations(self) -> dict[ComponentUid, list[KeyPath]]:
        found: dict[ComponentUid, list[KeyPath]] = {uid: [("parts", uid)] for uid in self.parts}
        for uid in self.devices:
            found.setdefault(uid, []).append(("devices", uid))
        for node_id, node in self.nodes.items():
            for uid in node.devices:
                found.setdefault(uid, []).append(("nodes", node_id, "devices", uid))
        return found

    @model_validator(mode="after")
    def _validate_component_graph(self) -> Self:
        """Require unique UIDs, and each device that a device names to run in the same process."""
        found = Problems()
        places = self._component_locations()
        for uid, (first, *others) in places.items():
            for place in others:
                msg = f"Component UID '{uid}' is duplicated: it is also written at {'.'.join(map(str, first))}"
                found.add("duplicate_uid", msg, *place)

        process = {uid: node_id for node_id, node in self.nodes.items() for uid in node.devices}
        unique = {uid: config for uid, config in self.all_devices.items() if len(places[uid]) == 1}
        for uid in unique:
            for dependency in dependencies(unique, uid):
                if process.get(dependency) != process.get(uid):
                    msg = (
                        f"Device '{uid}' references device '{dependency}', which runs in another process; "
                        "constructor-injected dependencies must be in the same process"
                    )
                    found.add("cross_node_reference", msg, *places[uid][0])

        found.raise_if_any(type(self).__name__)
        return self


__all__ = ["ComponentUid", "DeviceConfig", "NodeConfig", "NodeKind", "Parts", "RigConfig"]

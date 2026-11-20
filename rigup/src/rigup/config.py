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
ComponentId = Annotated[str, identifier("Component UID")]
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
    data = part.model_dump(mode=info.mode, exclude={"id"}, exclude_defaults=True)
    if type(part) is Part:
        return data
    return {"target": f"{type(part).__module__}.{type(part).__qualname__}", **data}


def _with_ids(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    entries: dict[Any, Any] = {}
    for device_id, entry in data.items():
        if isinstance(entry, Part) and entry.id != device_id:
            raise ValueError(f"the part '{entry.id}' is under the key '{device_id}'")
        entries[device_id] = {**entry, "id": device_id} if isinstance(entry, dict) else entry
    return entries


Parts = Annotated[
    dict[ComponentId, Annotated[Part, PlainValidator(_read_part), PlainSerializer(_write_part)]],
    BeforeValidator(_with_ids),
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
    devices: dict[ComponentId, DeviceConfig] = Field(default_factory=dict)

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
    devices: dict[ComponentId, DeviceConfig] = Field(default_factory=dict)
    nodes: dict[NodeId, NodeConfig] = Field(default_factory=dict)

    @property
    def all_devices(self) -> dict[ComponentId, DeviceConfig]:
        return {
            **self.devices,
            **{device_id: config for node in self.nodes.values() for device_id, config in node.devices.items()},
        }

    def component_location(self, device_id: ComponentId) -> KeyPath:
        """Return the key path of ``id`` in the rig file, or raise ``KeyError``."""
        if device_id in self.parts:
            return ("parts", device_id)
        if device_id in self.devices:
            return ("devices", device_id)
        for node_id, node in self.nodes.items():
            if device_id in node.devices:
                return ("nodes", node_id, "devices", device_id)
        raise KeyError(device_id)

    def _component_locations(self) -> dict[ComponentId, list[KeyPath]]:
        found: dict[ComponentId, list[KeyPath]] = {dev_id: [("parts", dev_id)] for dev_id in self.parts}
        for device_id in self.devices:
            found.setdefault(device_id, []).append(("devices", device_id))
        for node_id, node in self.nodes.items():
            for device_id in node.devices:
                found.setdefault(device_id, []).append(("nodes", node_id, "devices", device_id))
        return found

    @model_validator(mode="after")
    def _validate_component_graph(self) -> Self:
        """Require unique UIDs, and each device that a device names to run in the same process."""
        found = Problems()
        places = self._component_locations()
        for device_id, (first, *others) in places.items():
            for place in others:
                msg = f"Component UID '{device_id}' is duplicated: it is also written at {'.'.join(map(str, first))}"
                found.add("duplicate_id", msg, *place)

        process = {dev_id: node_id for node_id, node in self.nodes.items() for dev_id in node.devices}
        unique = {device_id: config for device_id, config in self.all_devices.items() if len(places[device_id]) == 1}
        for device_id in unique:
            for dependency in dependencies(unique, device_id):
                if process.get(dependency) != process.get(device_id):
                    msg = (
                        f"Device '{device_id}' references device '{dependency}', which runs in another process; "
                        "constructor-injected dependencies must be in the same process"
                    )
                    found.add("cross_node_reference", msg, *places[device_id][0])

        found.raise_if_any(type(self).__name__)
        return self


__all__ = ["ComponentId", "DeviceConfig", "NodeConfig", "NodeKind", "Parts", "RigConfig"]

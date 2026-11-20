"""The rig part of a legacy ``config.yaml``: ``devices`` and ``nodes``.

Shape::

    RigConfig
    ├── devices: dict[str, DeviceConfig]            # in-process (no node)
    └── nodes: dict[str, NodeConfig]
                ├── kind: "subprocess" | "remote"
                ├── address: str | None
                └── devices: dict[str, DeviceConfig]
"""

from typing import Annotated, Any, Literal, Self

import rigup.config
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rigup.build import dependencies
from vxlib.schema import duplicate_keys, identifier

from rigup import BuildConfig

NodeKind = Literal["subprocess", "remote"]
DeviceId = Annotated[str, identifier("Device UID")]
NodeId = Annotated[str, identifier("Node id")]


class DeviceConfig(BuildConfig):
    """Device construction and application-owned property persistence policy."""

    autosave: Literal["*"] | list[str] = Field(default_factory=list)

    def to_rig(self) -> rigup.config.DeviceConfig:
        """The config that rigup builds this device from. It shares ``init`` with this config."""
        return rigup.config.DeviceConfig.model_construct(target=self.target, init=self.init, defaults=self.defaults)


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "*"}


def _is_local_address(address: str) -> bool:
    """True if ``address`` names a local-only ZMQ endpoint.

    Local transports:
      - ``ipc://...`` — filesystem IPC, always local.
      - ``inproc://...`` — in-process only.
      - ``tcp://`` with host in ``{localhost, 127.0.0.1, ::1, *}`` (``*`` is the
        ZMQ bind-any form, e.g. ``tcp://*:5555``).
    """
    if address.startswith(("ipc://", "inproc://")):
        return True
    if not address.startswith("tcp://"):
        return False
    body = address[len("tcp://") :]
    # IPv6 bracket form: tcp://[::1]:port
    if body.startswith("["):
        closing = body.find("]")
        host = body[1:closing] if closing != -1 else body
    elif ":" in body:
        host = body.rsplit(":", 1)[0]
    else:
        host = body
    return host in _LOCAL_HOSTS


class NodeConfig(BaseModel):
    """Configuration for a single node in the rig.

    A node is always a separate process. In-process devices belong at the rig
    level, not inside a node.

    ``kind`` is autofilled from ``address`` when omitted:
      - no address → ``subprocess`` (cluster manager will assign one at spawn)
      - localhost-shaped address → ``subprocess``
      - anything else → ``remote``

    Explicit ``kind`` in the source always wins over autofill, so a remote
    node co-located on localhost is expressible with ``kind: remote`` +
    ``address: tcp://localhost:5555``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: NodeKind
    address: str | None = None
    devices: dict[DeviceId, DeviceConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _infer_kind(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "kind" in data:
            return data
        address = data.get("address")
        if address is None or _is_local_address(str(address)):
            data["kind"] = "subprocess"
        else:
            data["kind"] = "remote"
        return data

    @model_validator(mode="after")
    def _check_address(self) -> Self:
        if self.kind == "remote" and self.address is None:
            raise ValueError("remote node requires an address")
        # subprocess: address optional; cluster manager may assign an ephemeral one
        return self

    def to_rig(self) -> rigup.config.NodeConfig:
        """The config that rigup builds this node from."""
        devices = {device_id: config.to_rig() for device_id, config in self.devices.items()}
        return rigup.config.NodeConfig.model_construct(kind=self.kind, address=self.address, devices=devices)


class RigConfig(BaseModel, frozen=True):
    """Top-level rig configuration.

    ``devices`` declares in-process devices owned by the orchestrator itself —
    no IPC, no subprocess. ``nodes`` declares separate processes (subprocess or
    remote) that each host their own ``devices`` dict.
    """

    model_config = ConfigDict(extra="forbid")

    devices: dict[DeviceId, DeviceConfig] = Field(default_factory=dict)
    nodes: dict[NodeId, NodeConfig] = Field(default_factory=dict)

    @property
    def device_configs(self) -> dict[DeviceId, DeviceConfig]:
        """Every device of the rig, in-process and on each node, by UID."""
        configs = dict(self.devices)
        for node in self.nodes.values():
            configs.update(node.devices)
        return configs

    @property
    def device_ids(self) -> set[DeviceId]:
        """The UID of every device of the rig, in-process and on each node."""
        return set(self.device_configs)

    def to_rig(self) -> rigup.config.RigConfig:
        """The config that rigup builds from."""
        return rigup.config.RigConfig.model_construct(
            devices={device_id: config.to_rig() for device_id, config in self.devices.items()},
            nodes={node_id: node.to_rig() for node_id, node in self.nodes.items()},
        )

    @model_validator(mode="after")
    def _validate_device_graph(self) -> Self:
        """Require globally unique UIDs and keep injected object references within one process."""
        scopes = {"local": self.devices, **{f"node:{node_id}": node.devices for node_id, node in self.nodes.items()}}
        duplicates = duplicate_keys(scopes)
        errors = [
            f"Device UID '{device_id}' is duplicated across scopes: {', '.join(device_scopes)}"
            for device_id, device_scopes in duplicates.items()
        ]

        unique_owner = {
            dev_id: scope for scope, devices in scopes.items() for dev_id in devices if dev_id not in duplicates
        }
        unique = {
            device_id: config
            for devices in scopes.values()
            for device_id, config in devices.items()
            if device_id in unique_owner
        }

        for device_id, scope in unique_owner.items():
            for dependency in dependencies(unique, device_id):
                owner = unique_owner[dependency]
                if owner != scope:
                    errors.append(
                        f"Device '{device_id}' in scope '{scope}' references device '{dependency}' in scope '{owner}'; "
                        "constructor-injected device dependencies must be on the same node"
                    )

        if errors:
            raise ValueError("\n".join(errors))
        return self

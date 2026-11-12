"""Rig configuration schema.

Shape::

    RigConfig
    ├── components: dict[str, ComponentConfig]      # in-process (no node)
    └── nodes: dict[str, NodeConfig]
                ├── kind: "subprocess" | "remote"
                ├── address: str | None
                ├── allow_extras: bool
                └── components: dict[str, ComponentConfig]

In-process components live at the top level — they're Python objects in the
orchestrator's own process, with no address, no supervision, no coordination
beyond construction. A node, by contrast, is always a separate process.

A *subprocess* node is spawned by the cluster manager on the same host; its
lifetime is bound to the orchestrator. A *remote* node is externally
supervised (systemd/launchd/etc.) and connected to by address; the cluster
manager validates that the node's self-reported ``components`` config matches
what the rig declares (strict by default, with ``allow_extras`` to permit the
node to host components the rig doesn't care about).

``kind`` is autofilled from ``address`` when not given explicitly; see
:meth:`NodeConfig._infer_kind`.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from vxlib.schema import duplicate_keys, identifier

from .build import BuildConfig, dependencies

NodeKind = Literal["subprocess", "remote"]
ComponentUid = Annotated[str, identifier("Component UID")]
NodeId = Annotated[str, identifier("Node id")]


class ComponentConfig(BuildConfig):
    """How 1 device or part of the rig is built. ``details`` holds information for people: rigup does not read
    it, and the built component does not get it."""

    details: dict[str, Any] = Field(default_factory=dict)


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

    A node is always a separate process. In-process components belong at the rig
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
    components: dict[ComponentUid, ComponentConfig] = Field(default_factory=dict)

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


class RigConfig(BaseModel, frozen=True):
    """Top-level rig configuration.

    ``components`` declares the in-process devices and parts, owned by the
    orchestrator itself — no IPC, no subprocess. ``nodes`` declares separate
    processes (subprocess or remote) that each host their own ``components`` dict.
    """

    model_config = ConfigDict(extra="forbid")

    components: dict[ComponentUid, ComponentConfig] = Field(default_factory=dict)
    nodes: dict[NodeId, NodeConfig] = Field(default_factory=dict)

    @property
    def component_configs(self) -> dict[ComponentUid, ComponentConfig]:
        """Every component of the rig, in-process and on each node, by UID."""
        configs = dict(self.components)
        for node in self.nodes.values():
            configs.update(node.components)
        return configs

    @property
    def component_uids(self) -> set[ComponentUid]:
        """The UID of every component of the rig, in-process and on each node."""
        return set(self.component_configs)

    def references(self, uid: ComponentUid) -> set[ComponentUid]:
        """The components that the ``init`` of ``uid`` names."""
        return dependencies(self.component_configs, uid)

    @model_validator(mode="after")
    def _validate_component_graph(self) -> Self:
        """Require globally unique UIDs and keep injected object references within one process."""
        scopes = {
            "local": self.components,
            **{f"node:{node_id}": node.components for node_id, node in self.nodes.items()},
        }
        duplicates = duplicate_keys(scopes)
        errors = [
            f"Component UID '{uid}' is duplicated across scopes: {', '.join(found)}"
            for uid, found in duplicates.items()
        ]

        unique_owner = {uid: scope for scope, group in scopes.items() for uid in group if uid not in duplicates}
        unique = {uid: config for group in scopes.values() for uid, config in group.items() if uid in unique_owner}

        for uid, scope in unique_owner.items():
            for dependency in dependencies(unique, uid):
                owner = unique_owner[dependency]
                if owner != scope:
                    errors.append(
                        f"Component '{uid}' in scope '{scope}' references component '{dependency}' in scope '{owner}'; "
                        "constructor-injected dependencies must be on the same node"
                    )

        if errors:
            raise ValueError("\n".join(errors))
        return self


__all__ = ["ComponentConfig", "ComponentUid", "NodeConfig", "NodeKind", "RigConfig"]

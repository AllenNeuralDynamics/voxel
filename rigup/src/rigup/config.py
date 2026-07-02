"""Rig configuration schema.

Shape::

    RigConfig
    ├── devices: dict[str, DeviceConfig]            # in-process (no node)
    └── nodes: dict[str, NodeConfig]
                ├── kind: "subprocess" | "remote"
                ├── address: str | None
                ├── allow_extras: bool
                └── devices: dict[str, DeviceConfig]

In-process devices live at the top level — they're Python objects in the
orchestrator's own process, with no address, no supervision, no coordination
beyond construction. A node, by contrast, is always a separate process.

A *subprocess* node is spawned by the cluster manager on the same host; its
lifetime is bound to the orchestrator. A *remote* node is externally
supervised (systemd/launchd/etc.) and connected to by address; the cluster
manager validates that the node's self-reported ``devices`` config matches
what the rig declares (strict by default, with ``allow_extras`` to permit the
node to host devices the rig doesn't care about).

``kind`` is autofilled from ``address`` when not given explicitly; see
:meth:`NodeConfig._infer_kind`.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from .build import BuildConfig

NodeKind = Literal["subprocess", "remote"]

DeviceConfig = BuildConfig

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

    kind: NodeKind
    address: str | None = None
    devices: dict[str, DeviceConfig] = Field(default_factory=dict)

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

    ``devices`` declares in-process devices owned by the orchestrator itself —
    no IPC, no subprocess. ``nodes`` declares separate processes (subprocess or
    remote) that each host their own ``devices`` dict.
    """

    devices: dict[str, DeviceConfig] = Field(default_factory=dict)
    nodes: dict[str, NodeConfig] = Field(default_factory=dict)


__all__ = ["DeviceConfig", "NodeConfig", "NodeKind", "RigConfig"]

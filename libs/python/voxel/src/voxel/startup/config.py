"""System and hardware configuration models."""

import socket
from functools import cached_property
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from voxel.layout import LayoutDefinition
from voxel.presets import ChannelDefinition, ProfileDefinition
from voxel.instrument import InstrumentNodeType, InstrumentMetadata
from voxel.runtime.preview.models import PreviewManagerOptions, PreviewRelayOptions

from voxel.factory import BuildSpecs


class BaseNodeConfig(BaseModel):
    devices: BuildSpecs = Field(description="Devices available on the node, keyed by device uid")


class LocalNodeConfig(BaseNodeConfig):
    type: Literal[InstrumentNodeType.LOCAL] = InstrumentNodeType.LOCAL


class RemoteNodeConfig(BaseNodeConfig):
    type: Literal[InstrumentNodeType.REMOTE] = InstrumentNodeType.REMOTE
    host: str
    rpc_port: int
    ssh_user: str | None = None
    ssh_key: str | None = None
    ssh_port: int = 22


type NodeConfig = Annotated[LocalNodeConfig | RemoteNodeConfig, Field(discriminator="type")]


class SystemConfig(BaseModel):
    """Complete system definition including metadata and hardware."""

    metadata: InstrumentMetadata
    preview: PreviewManagerOptions = Field(default_factory=PreviewManagerOptions, description="Preview stream options")
    nodes: dict[str, NodeConfig]
    layout: LayoutDefinition

    @field_validator("nodes", mode="before")
    def set_missing_defaults(cls, raw_nodes):
        """Ensure all nodes have a type and default to remote if not specified."""
        out = {}
        for name, node in raw_nodes.items():
            if isinstance(node, dict) and "type" not in node:
                node_type = "remote" if "host" in node and "rpc_port" in node else "local"
                node = {**node, "type": node_type}  # copy so we don’t mutate the user’s dict in-place
            out[name] = node
        return out

    @field_validator("nodes", mode="after")
    def check_one_local_node(cls, nodes):
        locals_ = [name for name, node in nodes.items() if node.type == "local"]
        if len(locals_) != 1:
            raise ValueError(f"Exactly one local node required; found {len(locals_)}: {locals_}")
        return nodes

    @cached_property
    def preview_relay_opts(self) -> PreviewRelayOptions:
        return PreviewRelayOptions(
            manager_ip=socket.gethostbyname(socket.gethostname()),
            target_width=self.preview.target_width,
            publish_port=self.preview.listening_port,
        )

    @cached_property
    def remote_nodes(self) -> dict[str, "RemoteNodeConfig"]:
        """Return a list of remote worker nodes. Used to make a NodeClient for each worker."""
        return {name: node for name, node in self.nodes.items() if node.type == "remote"}


class InstrumentConfig(BaseModel, frozen=True):
    """
    Complete instrument definition including system and presets.
    This is used when starting a new experiment and will be copied to the experiment's working directory for use
    during acquisition.
    """

    system: SystemConfig
    channels: dict[str, ChannelDefinition]
    profiles: dict[str, ProfileDefinition]

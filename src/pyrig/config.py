"""Configuration models for rig startup."""

from typing import Any
from pydantic import BaseModel, Field
from pyrig.conn import get_local_ip
from ruyaml import YAML
from pathlib import Path
from rich import print

yaml = YAML(typ="safe")


class DeviceConfig(BaseModel):
    target: str  # Fully qualified class name, e.g., "pyrig.devices.camera.Camera"
    kwargs: dict[str, Any] = Field(default_factory=dict)  # Constructor arguments

    def get_device_class(self) -> type:
        """Dynamically import and return the device class."""
        parts = self.target.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid target format: {self.target}")

        module_name, class_name = parts

        import importlib

        module = importlib.import_module(module_name)
        device_class = getattr(module, class_name)

        return device_class


class NodeConfig(BaseModel):
    hostname: str = Field(default="127.0.0.1")
    devices: dict[str, DeviceConfig] = Field(default_factory=dict)


class RigMetadata(BaseModel):
    name: str
    control_port: int = Field(default=9000)  # Port for controller ROUTER socket


class RigConfig(BaseModel):
    """Complete rig configuration."""

    metadata: RigMetadata
    nodes: dict[str, NodeConfig]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RigConfig":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.load(f)
        # remove the key _anchors
        data.pop("_anchors", None)
        print(data)
        return cls.model_validate(data)

    @property
    def local_nodes(self) -> dict[str, NodeConfig]:
        local_hostnames = [get_local_ip(), "localhost", "127.0.0.1", "::1", None]
        return {uid: cfg for uid, cfg in self.nodes.items() if cfg.hostname in local_hostnames}

    @property
    def remote_nodes(self) -> dict[str, NodeConfig]:
        local_hosts = self.local_nodes
        return {uid: cfg for uid, cfg in self.nodes.items() if uid not in local_hosts}

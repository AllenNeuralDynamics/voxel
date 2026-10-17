from typing import Any, Literal, Self

from one_liner.models import RouterServerConfig  # type: ignore
from pydantic import BaseModel, ConfigDict, Field, model_validator
from vxlib.schema import FrozenModel

from rigup import RigConfig
from seqsweep.devices.acs.base import ScanPassConfig


class HandlerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    class_: str = Field(..., alias="class")
    level: str | None = None
    formatter: str | None = None
    filename: str | None = None


class LoggingConfig(BaseModel):
    version: Literal[1]
    disable_existing_loggers: bool = False
    formatters: dict[str, dict[str, Any]] | None = None
    handlers: dict[str, HandlerConfig] | None = None
    loggers: dict[str, dict[str, Any]] | None = None
    root: dict[str, Any] | None = None


class RouterServerPortConfig(BaseModel):
    rpc_port: int = 5555
    broadcast_port: int = 5556


class SeqSweepHardwareTopology(RigConfig, frozen=True):
    """The hardware blueprint (``hal``): a rig (``devices`` + ``nodes``, inherited) plus the role each device
    plays. Mirrors Voxel's ``HardwareTopology``: loaded once, never edited at runtime."""

    scan_controller: str = Field(description="UID of the scan controller in the rig")
    # TODO: cameras, lasers, z_axis roles

    @property
    def device_uids(self) -> set[str]:
        return set(self.devices) | {uid for node in self.nodes.values() for uid in node.devices}

    @model_validator(mode="after")
    def _check_roles(self) -> Self:
        if self.scan_controller not in self.device_uids:
            raise ValueError(f"scan_controller '{self.scan_controller}' is not a device in the rig")
        return self


class SeqSweepDefaults(FrozenModel):
    """Baseline run settings (``default``): the pass to run and how many times."""

    scan: ScanPassConfig
    passes: int = Field(default=2, ge=1)
    # TODO: pass timeouts, Z planes, strips


class SeqSweepInstrumentConfig(BaseModel):
    """A complete SeqSweep setup: the hardware blueprint (``hal``) and the baseline run settings (``default``)."""

    name: str = Field(default="seqsweep", min_length=1, description="Label for this setup in logs")
    hal: SeqSweepHardwareTopology
    default: SeqSweepDefaults


class SeqSweepSystemConfig(SeqSweepInstrumentConfig, validate_assignment=True):
    """The ``seqsweep`` ficus namespace: the instrument config plus the one_liner server and logging."""

    router_server_kwargs: RouterServerPortConfig = Field(default_factory=RouterServerPortConfig)
    router_server_api: RouterServerConfig
    logging: LoggingConfig

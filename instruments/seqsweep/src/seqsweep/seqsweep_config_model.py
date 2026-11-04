from typing import Any, Literal

from one_liner.models import RouterServerConfig  # type: ignore
from pydantic import BaseModel, ConfigDict, Field
from vxlib.schema import FrozenModel

from seqsweep.hal import SeqSweepHardwareTopology


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


class SeqSweepInstrumentDefaults(FrozenModel):
    """Baseline run settings (``default``): everything that can live in ``config.default``."""

    # TODO: scan settings (velocity, line pitch, lasers), passes, limits


class SeqSweepInstrumentConfig(BaseModel):
    """SeqSweep setup: the hardware blueprint (``hal``) and the baseline run settings (``default``)."""

    name: str = Field(default="seqsweep", min_length=1, description="Label for this setup in logs")
    hal: SeqSweepHardwareTopology = Field(
        description="Hardware blueprint: rigup devices and nodes, plus the role each device plays"
    )
    default: SeqSweepInstrumentDefaults = Field(
        default_factory=SeqSweepInstrumentDefaults, description="Baseline run settings; empty for now"
    )


class SeqSweepSystemConfig(SeqSweepInstrumentConfig, validate_assignment=True):
    """The ``seqsweep`` ficus namespace: the instrument config plus the one_liner server and logging."""

    router_server_kwargs: RouterServerPortConfig = Field(default_factory=RouterServerPortConfig)
    router_server_api: RouterServerConfig
    logging: LoggingConfig

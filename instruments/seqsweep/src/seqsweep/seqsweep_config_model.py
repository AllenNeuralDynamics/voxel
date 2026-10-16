from pathlib import Path
from typing import Any, Literal

from one_liner.models import RouterServerConfig  # type: ignore
from pydantic import BaseModel, ConfigDict, Field


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


class SeqSweepSystemConfig(BaseModel, validate_assignment=True):
    router_server_kwargs: RouterServerPortConfig = Field(default_factory=RouterServerPortConfig)
    router_server_api: RouterServerConfig
    scanner_config: Path = Field(
        default=Path("simulated-local.seqsweep.yaml"),
        description="SeqSweep config file, relative to the configs directory",
    )
    logging: LoggingConfig

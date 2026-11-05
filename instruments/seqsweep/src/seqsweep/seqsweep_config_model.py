from typing import Any, Literal, Self

from one_liner.models import RouterServerConfig  # type: ignore
from pydantic import BaseModel, ConfigDict, Field, model_validator
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


class OpticsConfig(FrozenModel):
    """TDI sensor and objective; sets the pixel size on the sample. No defaults: every derived value depends on these."""

    tdi_pixel_um: float = Field(..., gt=0, description="TDI sensor pixel size")
    magnification: float = Field(..., gt=0)
    tdi_image_width_px: int = Field(
        ..., gt=0, le=16384, multiple_of=32, description="Sensor width in pixels (long side, across the scan)"
    )
    overscan_px: int = Field(..., ge=0, description="Lead-in and lead-out distance outside the imaged range, in pixels")

    @property
    def pixel_size_um(self) -> float:
        """Pixel size on the sample."""
        return self.tdi_pixel_um / self.magnification

    @property
    def fov_y_um(self) -> float:
        """Strip width (y) on the sample."""
        return self.tdi_image_width_px * self.pixel_size_um

    @property
    def overscan_um(self) -> float:
        """Run-up and run-out outside the imaged range."""
        return self.overscan_px * self.pixel_size_um


class SeqSweepInstrumentDefaults(FrozenModel):
    """Baseline run settings (``default``): everything that can live in ``config.default``."""

    optics: OpticsConfig = Field(..., description="TDI camera and objective")
    chambers_y_mm: dict[int, float] = Field(
        default_factory=dict, description="Strip-axis (Y) start position of each sample chamber"
    )
    chamber_edge_margin_mm: float = Field(
        ..., gt=0, description="Clearance between the safe X range and the chamber edge; the overscan must fit in it"
    )
    x_safe_range_mm: tuple[float, float] | None = Field(
        default=None, description="X range kept clear of the sample chamber edges; passes are checked against it"
    )
    max_line_rate_hz: float | None = Field(
        default=None, gt=0, description="Camera line rate limit; keep in step with the camera config"
    )
    # TODO: lasers, passes

    @model_validator(mode="after")
    def _check_safe_range(self) -> Self:
        if self.x_safe_range_mm is not None and self.x_safe_range_mm[0] >= self.x_safe_range_mm[1]:
            raise ValueError("x_safe_range_mm must be [min, max]")
        overscan_mm = self.optics.overscan_um / 1000
        if overscan_mm > self.chamber_edge_margin_mm:
            raise ValueError(
                f"overscan {overscan_mm:g} mm ({self.optics.overscan_px} px) exceeds "
                f"chamber_edge_margin_mm {self.chamber_edge_margin_mm:g}"
            )
        return self


class SeqSweepInstrumentConfig(BaseModel):
    """SeqSweep setup: the hardware blueprint (``hal``) and the baseline run settings (``default``)."""

    name: str = Field(default="seqsweep", min_length=1, description="Label for this setup in logs")
    hal: SeqSweepHardwareTopology = Field(
        description="Hardware blueprint: rigup devices and nodes, plus the role each device plays"
    )
    default: SeqSweepInstrumentDefaults = Field(description="Baseline run settings")


class SeqSweepSystemConfig(SeqSweepInstrumentConfig, validate_assignment=True):
    """The ``seqsweep`` ficus namespace: the instrument config plus the one_liner server and logging."""

    router_server_kwargs: RouterServerPortConfig = Field(default_factory=RouterServerPortConfig)
    router_server_api: RouterServerConfig
    logging: LoggingConfig

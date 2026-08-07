"""Machine-local facts, config, and YAML I/O for the box this code runs on.

``System`` exposes what is true of *this* machine — CPU count, platform, hostname,
the RAM budget (:class:`System.Ram`), and the local storage roots (``store``/``scratch``).
Machine-specific knobs are sourced from ``VOXEL_*`` env vars, deliberately kept out of
the portable app config.

``load_yaml``/``save_yaml`` are re-exported from :mod:`vxlib` for compatibility.
"""

import logging
import socket
import sys
from pathlib import Path
from typing import ClassVar

import psutil
from dotenv import load_dotenv
from pydantic import AnyWebsocketUrl, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from vxlib import S3Store

log = logging.getLogger(__name__)


def _voxel_home() -> Path:
    """The fixed config/state home, ``~/.voxel`` -- holds ``system.yaml`` and ``instruments/``.
    Relocate it by setting ``$HOME``; move the data roots independently with
    ``VOXEL_STORE`` / ``VOXEL_SCRATCH``."""
    return Path.home() / ".voxel"


def load_voxel_env() -> None:
    """Load ``~/.voxel/.env`` into the process environment if present (a no-op when absent;
    existing vars win). A per-machine escape hatch for ambient settings the file layer can't
    reach: the ``VOXEL_*`` knobs *and* the AWS chain (``AWS_*``, ``S3_ENDPOINT_URL``) that
    s5cmd / boto3 / TensorStore read. Call once at startup, before constructing :class:`System`
    or any S3 client."""
    load_dotenv(_voxel_home() / ".env", override=False)


class Remote(S3Store):
    """A configured object store in the registry: the :class:`~vxlib.S3Store` connection plus the
    ``roots`` (display label -> write root) an operator may select. A root is a bucket, optionally
    narrowed by a key prefix (``bucket`` or ``bucket/prefix``). Extends the shared connection model
    with the UI catalog; still holds no secrets -- credentials come from the AWS chain."""

    roots: dict[str, str] = Field(default_factory=dict, description="display label -> bucket or bucket/prefix")


class System(BaseSettings):
    """This machine: ``VOXEL_*`` env knobs, the ``system.yaml`` config, and introspected facts.

    Construct to read and validate the environment plus ``~/.voxel/system.yaml`` (init > env >
    yaml). Exposes the local storage roots (``store``/``scratch``, overridable via
    ``VOXEL_STORE``/``VOXEL_SCRATCH``), the optional external preview WebSocket URL and outbound
    instrument/preview publisher endpoints, the
    object-store registry (:attr:`remotes`), the fixed config home (:attr:`dir`), the pure machine
    facts (``cpu_count``/``platform``/``hostname``), and the shared RAM budget (:class:`Ram`). Paths
    are resolved only; whoever writes creates them.
    """

    model_config = SettingsConfigDict(env_prefix="VOXEL_", extra="ignore")

    store: Path = Field(default_factory=lambda: _voxel_home() / "store", description="VOXEL_STORE")
    scratch: Path = Field(default_factory=lambda: _voxel_home() / "scratch", description="VOXEL_SCRATCH")
    max_ram_fraction: float = Field(default=0.75, gt=0.0, le=1.0)
    preview_url: AnyWebsocketUrl | None = None
    instrument_feed_endpoint: str | None = Field(
        default=None,
        min_length=1,
        description="ZMQ endpoint where the instrument state publisher connects",
    )
    preview_frame_endpoint: str | None = Field(
        default=None,
        min_length=1,
        description="ZMQ endpoint where the preview frame publisher connects",
    )
    remotes: dict[str, Remote] = Field(
        default_factory=dict, description="object-store name -> connection (from ~/.voxel/system.yaml)"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer ``~/.voxel/system.yaml`` under the env (priority: init > env > yaml). The yaml
        carries structured config -- notably :attr:`remotes` -- that flat env vars can't express."""
        del dotenv_settings, file_secret_settings
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=_voxel_home() / "system.yaml")
        return (init_settings, env_settings, yaml_source)

    @property
    def dir(self) -> Path:
        """The fixed config/state home (``~/.voxel``); see :func:`_voxel_home`."""
        return _voxel_home()

    @field_validator("store", "scratch", mode="after")
    @classmethod
    def _expand(cls, p: Path) -> Path:
        return p.expanduser()

    @staticmethod
    def cpu_count() -> int:
        return psutil.cpu_count(logical=True) or 1

    @staticmethod
    def platform() -> str:
        return sys.platform

    @staticmethod
    def hostname() -> str:
        return socket.gethostname()

    class Ram:
        """Weighted RAM-budget mediation for consumers sharing this machine's memory.

        Holds a policy fraction of available RAM and divides it among registered
        consumers in proportion to their weights. Consumers register via
        ``reserve()`` / ``release()`` and read their allocation via ``reserved()``.
        """

        _consumers: ClassVar[dict[str, float]] = {}

        @classmethod
        def total_bytes(cls) -> int:
            return psutil.virtual_memory().total

        @classmethod
        def available_bytes(cls) -> int:
            return psutil.virtual_memory().available

        @classmethod
        def max_bytes(cls) -> int:
            """Live policy cap: available system RAM * VOXEL_MAX_RAM_FRACTION."""
            return int(cls.available_bytes() * System().max_ram_fraction)

        @classmethod
        def reserve(cls, consumer_id: str, weight: float = 1.0) -> int:
            """Register ``consumer_id`` with ``weight``; return its share in bytes."""
            if weight <= 0:
                raise ValueError(f"weight must be > 0, got {weight}")
            cls._consumers[consumer_id] = weight
            return cls.reserved(consumer_id)

        @classmethod
        def release(cls, consumer_id: str) -> None:
            """Deregister ``consumer_id`` (no-op if not registered)."""
            cls._consumers.pop(consumer_id, None)

        @classmethod
        def reserved(cls, consumer_id: str) -> int:
            """Return the consumer's current weighted share in bytes.

            Raises KeyError if the consumer hasn't been registered via reserve().
            """
            if consumer_id not in cls._consumers:
                raise KeyError(consumer_id)
            total_weight = sum(cls._consumers.values()) or 1.0
            return int(cls.max_bytes() * cls._consumers[consumer_id] / total_weight)

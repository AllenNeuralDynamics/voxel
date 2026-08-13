"""Machine-local facts and configuration for the box this code runs on.

``System`` exposes what is true of *this* machine — CPU count, platform, hostname,
the RAM budget (:class:`System.Ram`), and the local storage roots (``store``/``scratch``).
Machine-specific knobs are sourced from ``VOXEL_*`` env vars and one machine file. A
control station's ``station.yaml`` is a superset of ``system.yaml`` and takes its place
when present; nodes and other non-control processes can use ``system.yaml`` or defaults.

``load_yaml``/``save_yaml`` are re-exported from :mod:`vxlib` for compatibility.
"""

import logging
import socket
import sys
from hashlib import sha256
from pathlib import Path
from typing import ClassVar, Literal, Self
from uuid import UUID, uuid4

import psutil
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from vxlib import S3Store, save_yaml

log = logging.getLogger(__name__)


def _voxel_home() -> Path:
    """The fixed config/state home, ``~/.voxel`` -- holds machine config and ``instruments/``.
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


class Remote(BaseModel):
    """A configured object store in the registry: the :class:`~vxlib.S3Store` ``connection`` plus the
    ``roots`` (display label -> write root) an operator may select. A root is a bucket, optionally
    narrowed by a key prefix (``bucket`` or ``bucket/prefix``). Holds no secrets -- credentials come
    from the AWS chain.

    The connection is held, not inherited: ``roots`` is operator-facing catalog data, while a
    :class:`~vxlib.S3Store` is a frozen *value* that writers hash to key their S3 client per
    connection. Subclassing would make a ``Remote`` an unhashable ``S3Store`` -- accepted by every
    ``store:`` field, then failing inside a cache lookup layers away. Pass ``.connection``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection: S3Store = S3Store()
    roots: dict[str, str] = Field(default_factory=dict, description="display label -> bucket or bucket/prefix")


def remote_store_fingerprint(store: S3Store) -> str:
    """Return a non-secret identity for matching one object store across machines.

    Roots and credential strategies are deliberately excluded: machines may expose different selectable roots and
    use different credentials while addressing the same S3-compatible service.
    """
    identity = f"{store.endpoint or ''}\0{store.region or ''}".encode()
    return f"s3:{sha256(identity).hexdigest()}"


class System(BaseSettings):
    """This machine: ``VOXEL_*`` env knobs, machine YAML config, and introspected facts.

    Construct to read and validate the environment plus ``~/.voxel/station.yaml`` when it exists,
    otherwise ``~/.voxel/system.yaml`` (init > env > yaml). The selected file is not merged with
    the fallback. Exposes the local storage roots (``store``/``scratch``, overridable via
    ``VOXEL_STORE``/``VOXEL_SCRATCH``), the object-store registry (:attr:`remotes`), the fixed config
    home (:attr:`dir`), the pure machine
    facts (``cpu_count``/``platform``/``hostname``), and the shared RAM budget (:class:`Ram`). Paths
    are resolved only; whoever writes creates them.
    """

    model_config = SettingsConfigDict(env_prefix="VOXEL_", extra="ignore")

    store: Path = Field(default_factory=lambda: _voxel_home() / "store", description="VOXEL_STORE")
    scratch: Path = Field(default_factory=lambda: _voxel_home() / "scratch", description="VOXEL_SCRATCH")
    max_ram_fraction: float = Field(
        default=0.75,
        gt=0.0,
        le=1.0,
        description=(
            "VOXEL_MAX_RAM_FRACTION — fraction of *available* (not total) RAM that registered consumers "
            "divide between them by weight. Because the denominator excludes the OS and other processes, "
            "this is a share of what is free at the moment it is read, not a fixed provision."
        ),
    )
    remotes: dict[str, Remote] = Field(
        default_factory=dict, description="object-store name -> connection (from the selected machine config)"
    )

    @classmethod
    def config_path(cls) -> Path:
        """Return the selected machine config: station first, then system.

        Selection is whole-file precedence, not a merge. This keeps exactly one authority for
        structured machine settings while allowing nodes to run without a station identity.
        """
        station = _voxel_home() / "station.yaml"
        return station if station.is_file() else _voxel_home() / "system.yaml"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer the selected machine YAML under env (priority: init > env > yaml)."""
        del dotenv_settings, file_secret_settings
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=cls.config_path())
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


class StationInfo(BaseModel):
    """Stable public identity of a Voxel control station."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str


class _SystemFieldsEnvSource(EnvSettingsSource):
    """Restrict station env overrides to machine policy; identity remains file-backed."""

    def __call__(self) -> dict[str, object]:
        return {key: value for key, value in super().__call__().items() if key in System.model_fields}


class StationConfig(System):
    """Persisted control-station identity plus the complete local :class:`System` config.

    Unlike :class:`System`, this configuration never falls back to ``system.yaml``. Control
    entrypoints use :meth:`load` so a missing station is reported clearly; remote nodes continue
    to construct ``System`` and therefore need no station identity. The live station authority is
    intentionally a separate concept from this settings model.
    """

    schema_version: Literal[1] = 1
    id: UUID
    name: str = Field(min_length=1)

    @classmethod
    def config_path(cls) -> Path:
        """Return the required control-station configuration path."""
        return _voxel_home() / "station.yaml"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read station YAML only; ``system.yaml`` is not a second configuration authority."""
        del env_settings, dotenv_settings, file_secret_settings
        return (
            init_settings,
            _SystemFieldsEnvSource(settings_cls),
            YamlConfigSettingsSource(settings_cls, yaml_file=cls.config_path()),
        )

    @classmethod
    def load(cls) -> Self:
        """Load the control station or explain how to initialize one."""
        # Import lazily because ``vxl.station`` models depend on ``StationInfo`` from this module.
        from vxl.station.errors import StationNotConfiguredError  # noqa: PLC0415

        path = cls.config_path()
        if not path.is_file():
            raise StationNotConfiguredError(
                f"No control station configured at {path}. Initialize one with `vxl station init --name <name>`."
            )
        return cls()  # pyright: ignore[reportCallIssue] -- required fields come from the checked YAML source

    @classmethod
    def initialize(cls, name: str, *, station_id: UUID | None = None) -> Self:
        """Create ``station.yaml`` from the effective System config, refusing to overwrite it."""
        path = cls.config_path()
        if path.exists():
            raise FileExistsError(f"A control station is already configured at {path}")

        system = System()
        station_config = cls(
            schema_version=1,
            id=station_id or uuid4(),
            name=name,
            store=system.store,
            scratch=system.scratch,
            max_ram_fraction=system.max_ram_fraction,
            remotes=system.remotes,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(path, station_config)
        return station_config

    @property
    def info(self) -> StationInfo:
        """Return the bounded station identity safe to expose to clients."""
        return StationInfo(id=self.id, name=self.name)


__all__ = ["Remote", "StationConfig", "StationInfo", "System", "load_voxel_env", "remote_store_fingerprint"]

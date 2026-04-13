"""Voxel system configuration.

Combines user-settable preferences (loaded from ``~/.voxel/system.yaml``) with
machine-introspected facts exposed as read-only properties. One object, both
sources of truth: YAML for what the user chose, psutil for what the machine is.

YAML loading routes through a custom ruyaml-backed source so the project stays
on a single YAML parser (ruyaml, already a dep) rather than pulling in PyYAML
via pydantic-settings' stock YAML source.
"""

import logging
import socket
import sys
from pathlib import Path
from typing import Any, ClassVar

import psutil
from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from ruyaml import YAML

from vxl.config import DataRoot

log = logging.getLogger(__name__)

VOXEL_DIR = Path.home() / ".voxel"
SYSTEM_CONFIG_PATH = VOXEL_DIR / "system.yaml"


class RuyamlConfigSettingsSource(InitSettingsSource):
    """Pydantic-settings source that loads from YAML via ruyaml.

    Slots into the same priority layering as the stock YamlConfigSettingsSource
    by subclassing InitSettingsSource with the loaded dict, but uses ruyaml
    (already a dep) instead of PyYAML.
    """

    def __init__(self, settings_cls: type[BaseSettings], yaml_file: Path) -> None:
        init_kwargs: dict[str, Any] = {}
        if yaml_file.is_file():
            loaded = YAML(typ="safe").load(yaml_file.read_text())
            if loaded:
                init_kwargs = dict(loaded)
        super().__init__(settings_cls, init_kwargs)


class SystemConfig(BaseSettings):
    """Voxel system configuration — user preferences + machine facts.

    User-settable fields load from ``~/.voxel/system.yaml`` (if present), with
    env var overrides (``VOXEL_*``) and init kwargs taking precedence. Machine
    facts (RAM, CPU, platform, hostname) are exposed as read-only properties
    that query psutil/stdlib on access.

    Construct via ``SystemConfig.load()`` to also materialize the
    ``~/.voxel/`` directory structure on first run. Direct construction
    (``SystemConfig()``) skips that step and just loads whatever YAML exists.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOXEL_",
        extra="ignore",
    )

    # ==================== User-settable preferences ====================

    data_roots: list[DataRoot] = Field(default_factory=list)

    max_ram_fraction: float = Field(
        default=0.75,
        gt=0.0,
        le=1.0,
        description="Fraction of total RAM voxel may use for writer buffers and pipelines.",
    )

    @field_validator("data_roots", mode="after")
    @classmethod
    def _expand_root_paths(cls, v: list[DataRoot]) -> list[DataRoot]:
        """Ensure every DataRoot's path is expanded and resolved."""
        return [root.model_copy(update={"path": root.path.expanduser().resolve()}) for root in v]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Source priority: init kwargs > YAML file > env vars > .env > secrets."""
        return (
            init_settings,
            RuyamlConfigSettingsSource(settings_cls, yaml_file=SYSTEM_CONFIG_PATH),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    # ==================== First-run initialization ====================

    @classmethod
    def initialize_defaults(cls) -> None:
        """Create the ``~/.voxel/`` directory structure and default system.yaml."""
        VOXEL_DIR.mkdir(parents=True, exist_ok=True)
        data_dir = VOXEL_DIR / "data"
        data_dir.mkdir(exist_ok=True)

        defaults: dict[str, Any] = {
            "data_roots": [
                {
                    "name": "local",
                    "label": "Local Storage",
                    "path": str(data_dir),
                    "default": True,
                },
            ],
        }
        yaml = YAML()
        yaml.preserve_quotes = True  # type: ignore[assignment]
        with SYSTEM_CONFIG_PATH.open("w") as f:
            yaml.dump(defaults, f)
        log.info("Created system config: %s", SYSTEM_CONFIG_PATH)

    @classmethod
    def load(cls) -> "SystemConfig":
        """Load SystemConfig, creating ``~/.voxel/`` defaults on first run.

        Also propagates ``max_ram_fraction`` into the ``System`` class-singleton
        so subsequent ``System.max_ram_bytes()`` / ``reserve_ram()`` / etc. use
        the configured value.
        """
        if not SYSTEM_CONFIG_PATH.exists():
            log.info("First run detected, creating ~/.voxel/ directory structure")
            cls.initialize_defaults()
        cfg = cls()
        System.configure(cfg.max_ram_fraction)
        return cfg


class System:
    """Process-global machine state and RAM-budget mediation.

    Class-level singleton: every method is a classmethod, no instances exist.
    Combines machine introspection (``cpu_count``, ``*_ram_bytes``, ``platform``,
    ``hostname``) with weighted RAM-budget mediation for consumers on this host.

    Defaults to ``max_ram_fraction=0.75``; call ``configure()`` to override
    (typically done automatically by ``SystemConfig.load()`` from YAML).
    Call ``reset()`` in tests for a clean slate.
    """

    _max_ram_fraction: ClassVar[float] = 0.75
    _consumers: ClassVar[dict[str, float]] = {}

    # ==================== Configuration ====================

    @classmethod
    def configure(cls, max_ram_fraction: float) -> None:
        """Set the policy fraction for RAM budget math."""
        if not 0.0 < max_ram_fraction <= 1.0:
            raise ValueError(f"max_ram_fraction must be in (0, 1], got {max_ram_fraction}")
        cls._max_ram_fraction = max_ram_fraction

    @classmethod
    def max_ram_fraction(cls) -> float:
        return cls._max_ram_fraction

    # ==================== Machine introspection (non-resource-specific) ====================

    @classmethod
    def cpu_count(cls) -> int:
        return psutil.cpu_count(logical=True) or 1

    @classmethod
    def platform(cls) -> str:
        return sys.platform

    @classmethod
    def hostname(cls) -> str:
        return socket.gethostname()

    # ==================== RAM introspection ====================

    @classmethod
    def total_ram_bytes(cls) -> int:
        return psutil.virtual_memory().total

    @classmethod
    def available_ram_bytes(cls) -> int:
        return psutil.virtual_memory().available

    @classmethod
    def max_ram_bytes(cls) -> int:
        """Live policy cap: available_ram_bytes * max_ram_fraction."""
        return int(cls.available_ram_bytes() * cls._max_ram_fraction)

    # ==================== RAM budget operations ====================

    @classmethod
    def reserve_ram(cls, consumer_id: str, weight: float = 1.0) -> int:
        """Register ``consumer_id`` with ``weight``; return current share in bytes."""
        if weight <= 0:
            raise ValueError(f"weight must be > 0, got {weight}")
        cls._consumers[consumer_id] = weight
        return cls.ram_share(consumer_id)

    @classmethod
    def release_ram(cls, consumer_id: str) -> None:
        """Deregister ``consumer_id`` (no-op if not registered)."""
        cls._consumers.pop(consumer_id, None)

    @classmethod
    def ram_share(cls, consumer_id: str) -> int:
        """Return the consumer's current weighted share in bytes.

        Raises KeyError if the consumer hasn't been registered via reserve_ram().
        """
        if consumer_id not in cls._consumers:
            raise KeyError(consumer_id)
        total_weight = sum(cls._consumers.values()) or 1.0
        return int(cls.max_ram_bytes() * cls._consumers[consumer_id] / total_weight)

    @classmethod
    def ram_reserved(cls, consumer_id: str) -> bool:
        """Return True if ``consumer_id`` currently has a RAM reservation."""
        return consumer_id in cls._consumers

    # ==================== Test support ====================

    @classmethod
    def reset(cls) -> None:
        """Reset to pristine state — primarily for tests."""
        cls._consumers = {}
        cls._max_ram_fraction = 0.75

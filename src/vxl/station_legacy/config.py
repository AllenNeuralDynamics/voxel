"""The configuration of a control station: its identity and the local :class:`System` settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource

from vxl import system
from vxl._utils.files import save_yaml
from vxl.metadata import BASE_METADATA_SCHEMA, resolve_metadata_class
from vxl.system import System

if TYPE_CHECKING:
    from pathlib import Path


class StationNotConfiguredError(FileNotFoundError):
    """Raised when a control application is started without ``station.yaml``."""


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
    metadata_schemas: dict[str, str] = Field(
        default_factory=dict, description="menu name -> dotted path of an ExperimentMetadata subclass"
    )

    @field_validator("metadata_schemas")
    @classmethod
    def _check_metadata_schemas(cls, value: dict[str, str]) -> dict[str, str]:
        for name, target in value.items():
            try:
                resolve_metadata_class(target)
            except (ImportError, AttributeError, TypeError, ValueError) as error:
                raise ValueError(f"'{name}': {error}") from error
        return value

    def metadata_menu(self) -> dict[str, str]:
        """The metadata forms that this station offers: the base form, then those of ``metadata_schemas``."""
        return {"Base": BASE_METADATA_SCHEMA, **self.metadata_schemas}

    @classmethod
    def config_path(cls) -> Path:
        """Return the required control-station configuration path."""
        return system.voxel_home() / "station.yaml"

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
            system.yaml_source(settings_cls, cls.config_path()),
        )

    @classmethod
    def load(cls) -> Self:
        """Load the control station or explain how to initialize one."""
        path = cls.config_path()
        if not path.is_file():
            raise StationNotConfiguredError(
                f"No control station configured at {path}. Initialize one with `vxl init-legacy --name <name>`."
            )
        return cls()  # pyright: ignore[reportCallIssue] -- required fields come from the checked YAML source

    @classmethod
    def initialize(cls, name: str, *, station_id: UUID | None = None) -> Self:
        """Create ``station.yaml`` from the effective System config, refusing to overwrite it."""
        path = cls.config_path()
        if path.exists():
            raise FileExistsError(f"A control station is already configured at {path}")

        machine = System()
        station_config = cls(
            schema_version=1,
            id=station_id or uuid4(),
            name=name,
            store=machine.store,
            scratch=machine.scratch,
            max_ram_fraction=machine.max_ram_fraction,
            remotes=machine.remotes,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(path, station_config)
        return station_config

    @property
    def info(self) -> StationInfo:
        """Return the bounded station identity safe to expose to clients."""
        return StationInfo(id=self.id, name=self.name)


__all__ = ["StationConfig", "StationInfo", "StationNotConfiguredError"]

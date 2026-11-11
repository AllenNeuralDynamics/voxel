"""The files of a station and of an instrument: ``station.yaml``, ``config.yaml`` and ``state.json``."""

import secrets
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Self, cast
from uuid import UUID, uuid4

from ome_zarr_writer import WriterSettings
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, EnvSettingsSource, PydanticBaseSettingsSource
from ruamel.yaml import YAML
from vxlib.schema import FrozenModel

from vxl import system
from vxl._utils.files import save_yaml
from vxl.hal_next.config import HALConfig
from vxl.hal_next.errors import Violation, under
from vxl.system import System

from .errors import StationNotConfiguredError
from .metadata import BASE_METADATA_SCHEMA, ExperimentMetadata, MetadataCls, resolve_metadata_class

# === The station ===


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
                f"No control station configured at {path}. Initialize one with `vxl station init --name <name>`."
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


# === An instrument ===

_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
"""Crockford's base32 in lowercase: digits and letters without i, l, o and u, which are easy to misread."""

InstrumentId = Annotated[str, Field(pattern=f"^[0-7][{_ID_ALPHABET}]{{25}}$")]
"""128 random bits in 26 characters, safe in URLs and file names."""

InstrumentName = Annotated[str, Field(min_length=1, max_length=32)]
"""A label for people."""

InstrumentModel = Annotated[str, Field(min_length=1, max_length=64)]
"""The lab's own label for the kind of instrument, such as ``exaSPIM`` or ``exaspim.v2``."""

InstrumentKind = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")]
"""The package of the code that runs the instrument, such as ``vxl.instruments.spim``."""


def new_instrument_id() -> str:
    value = secrets.randbits(128)
    return "".join(_ID_ALPHABET[(value >> shift) & 31] for shift in range(125, -1, -5))


class _NotDefault:
    def __repr__(self) -> str:
        return "NotDefault"


NotDefault = _NotDefault()
"""The mark of a state field that is about the specimen on the stage, and not about the instrument. Such a field is
never saved as a default: ``plan: Annotated[list[Task], NotDefault]``."""


class InstrumentState[H: HALConfig](FrozenModel):
    """What the operator edits. ``state.json`` has this form, and so do ``config.default`` and a preset. A kind of
    instrument adds its own fields in a subclass. ``metadata`` is the facts about the specimen, in the form that
    ``metadata_cls`` gives."""

    metadata_cls: MetadataCls = ExperimentMetadata
    output: WriterSettings = Field(default_factory=WriterSettings)
    metadata: Annotated[dict[str, Any], NotDefault] = Field(default_factory=dict)

    @classmethod
    def default_fields(cls) -> frozenset[str]:
        """The fields that can be saved as a default: those with no ``NotDefault`` mark."""
        return frozenset(name for name, field in cls.model_fields.items() if NotDefault not in field.metadata)

    def as_preset(self) -> Self:
        """This state with no specimen metadata."""
        return self.model_copy(update={"metadata": {}})

    def violations(self, hal: H) -> list[Violation]:
        """Return the problems of this state against ``hal``."""
        del hal
        return []


class InstrumentTemplate[H: HALConfig, S: InstrumentState[Any]](FrozenModel):
    """A shipped instrument design: an instrument file without an ID or a name."""

    model: InstrumentModel | None = None
    kind: InstrumentKind
    hal: H
    default: S

    def violations(self) -> list[Violation]:
        """Return the problems that the file shows."""
        return [*under(("hal",), self.hal.violations()), *under(("default",), self.default.violations(self.hal))]


class InstrumentConfig[H: HALConfig, S: InstrumentState[Any]](FrozenModel):
    """An instrument's ``config.yaml``. Its ID is made when the instrument is created and never changes. ``kind``
    names the code that runs the instrument; a subclass gives its own in ``KIND``. ``default`` has the fields of the
    state that can be saved as a default, and no others."""

    KIND: ClassVar[str]

    id: InstrumentId
    name: InstrumentName
    model: InstrumentModel | None = None
    kind: InstrumentKind
    hal: H
    default: S

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind != self.KIND:
            raise ValueError(f"kind: this file is for '{self.kind}', and this is '{self.KIND}'")
        for name, field in type(self.default).model_fields.items():
            if NotDefault in field.metadata and getattr(self.default, name) != field.get_default(
                call_default_factory=True
            ):
                raise ValueError(f"default.{name}: '{name}' is not saved as a default")
        return self

    @field_serializer("default", mode="wrap")
    def _dump_default(self, value: S, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = cast("dict[str, Any]", handler(value))
        fields = value.default_fields()
        return {name: found for name, found in data.items() if name in fields}

    @classmethod
    def state_class(cls) -> type[S]:
        """The class of this kind's state."""
        return cast("type[S]", cls.model_fields["default"].annotation)

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate 1 instrument file."""
        return cls.model_validate(YAML(typ="safe").load(path.read_text(encoding="utf-8")))

    @classmethod
    def from_template(cls, template: InstrumentTemplate[H, S], name: str) -> Self:
        """Make a new instrument from a design, with a new ID."""
        return cls.model_validate({"id": new_instrument_id(), "name": name, **dict(template)})

    def violations(self) -> list[Violation]:
        """Return the problems that the file shows."""
        return [*under(("hal",), self.hal.violations()), *under(("default",), self.default.violations(self.hal))]

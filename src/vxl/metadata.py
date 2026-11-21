"""Experiment metadata models for Voxel sessions."""

import importlib
from collections.abc import Mapping
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer
from pydantic.fields import FieldInfo
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

BASE_METADATA_SCHEMA = "vxl.metadata.ExperimentMetadata"


def annotation(**kwargs: Any) -> Any:
    """Mark a metadata field as an annotation (editable post-acquisition).

    Unmarked fields are provenance by default (locked after first acquisition).
    """
    extra = kwargs.pop("json_schema_extra", None) or {}
    extra["isAnnotation"] = True
    return Field(**kwargs, json_schema_extra=extra)


def key(**kwargs: Any) -> Any:
    """Mark a metadata field as the key of its class: tasks with the same value in it are about the same thing, such
    as 1 subject. A class has at most 1 key field."""
    extra = kwargs.pop("json_schema_extra", None) or {}
    extra["isKey"] = True
    return Field(**kwargs, json_schema_extra=extra)


def required(**kwargs: Any) -> Any:
    """Mark a metadata field as required: an acquisition does not start while a task leaves it empty. The field
    keeps a default, so a new task can be made before it is filled in. The key field is always required."""
    extra = kwargs.pop("json_schema_extra", None) or {}
    extra["isRequired"] = True
    return Field(**kwargs, json_schema_extra=extra)


class ExperimentMetadata(BaseModel):
    """Base class for experiment metadata.

    Subclass to define custom schemas for different instruments or labs.
    Fields are provenance by default — use ``annotation()`` instead of ``Field()``
    for fields that should remain editable after acquisition starts, and ``required()`` for fields that must be filled
    in before one starts. A nested model is a group of fields. At most 1
    field is made with ``key()``; a class with more raises :class:`TypeError` when it is defined.
    """

    model_config = {"extra": "forbid"}

    notes: str = annotation(default="", description="Experiment notes")

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if len(keys := cls._marked("isKey")) > 1:
            raise TypeError(f"{cls.__name__} has more than 1 key field: {sorted(keys)}")

    @classmethod
    def _marked(cls, mark: str) -> set[str]:
        names: set[str] = set()
        for name, field_info in cls.model_fields.items():
            extra = field_info.json_schema_extra
            if isinstance(extra, dict) and extra.get(mark):
                names.add(name)
        return names

    @classmethod
    def annotation_fields(cls) -> set[str]:
        """Return the set of field names marked as annotations."""
        return cls._marked("isAnnotation")

    @classmethod
    def key_field(cls) -> str | None:
        """Return the name of the field marked as the key, or ``None`` when the class has none."""
        return next(iter(cls._marked("isKey")), None)

    @classmethod
    def empty_required(cls, values: Mapping[str, Any]) -> list[tuple[tuple[str, ...], str]]:
        """Return each required field that ``values`` leaves empty, as its path and its title. A field inside a
        group has the group's name first in its path. Empty is ``None``, text with nothing but spaces, an empty list
        or an empty map."""
        return cls._empty_in(cls, values)

    @classmethod
    def merged(cls, values: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
        """Return ``values`` with ``changes`` over them. A group is changed field by field: its fields that
        ``changes`` does not name keep their values. Any other value, such as a map of free keys, is replaced whole."""
        return cls._merged_in(cls, values, changes)

    @staticmethod
    def _group(info: FieldInfo) -> type[BaseModel] | None:
        """The model of a field that is a group, also when the group may be ``None``."""
        options = [info.annotation, *get_args(info.annotation)]
        return next((option for option in options if isinstance(option, type) and issubclass(option, BaseModel)), None)

    @staticmethod
    def _empty_in(form: type[BaseModel], values: Mapping[str, Any]) -> list[tuple[tuple[str, ...], str]]:
        found: list[tuple[tuple[str, ...], str]] = []
        for name, info in form.model_fields.items():
            value = values.get(name)
            extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
            if (group := ExperimentMetadata._group(info)) is not None and isinstance(value, Mapping):
                found += [((name, *path), title) for path, title in ExperimentMetadata._empty_in(group, value)]
                continue
            empty = value in (None, [], {}) or (isinstance(value, str) and not value.strip())
            if empty and (extra.get("isRequired") or extra.get("isKey")):
                found.append(((name,), info.title or name.replace("_", " ").capitalize()))
        return found

    @staticmethod
    def _merged_in(form: type[BaseModel], values: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(values)
        for name, change in changes.items():
            info, value = form.model_fields.get(name), merged.get(name)
            group = None if info is None else ExperimentMetadata._group(info)
            if group is not None and isinstance(value, Mapping) and isinstance(change, Mapping):
                merged[name] = ExperimentMetadata._merged_in(group, value, change)
            else:
                merged[name] = change
        return merged

    @classmethod
    def model_json_schema(
        cls,
        by_alias: bool = True,
        ref_template: str = "#/$defs/{model}",
        schema_generator: type[GenerateJsonSchema] = GenerateJsonSchema,
        mode: JsonSchemaMode = "validation",
        *,
        union_format: Literal["any_of", "primitive_type_array"] = "any_of",
    ) -> dict[str, Any]:
        schema = super().model_json_schema(
            by_alias=by_alias,
            ref_template=ref_template,
            schema_generator=schema_generator,
            mode=mode,
            union_format=union_format,
        )
        annotations = cls.annotation_fields()
        for name, prop in schema.get("properties", {}).items():
            prop["isAnnotation"] = name in annotations
        return schema


def resolve_metadata_class(target: str) -> type[ExperimentMetadata]:
    """Import a metadata class from a dotted target path (e.g. ``vxl_drivers.metadata.ExaspimMetadata``)."""
    module_path, class_name = target.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (isinstance(cls, type) and issubclass(cls, ExperimentMetadata)):
        raise TypeError(f"{target} is not an ExperimentMetadata subclass")
    return cls


def resolve_class_from_path(v: Any) -> type[ExperimentMetadata]:
    """Deserializer: String -> Class (Runs when loading JSON)"""
    # If it's already a class (e.g. instantiated in code), just return it
    if isinstance(v, type) and issubclass(v, ExperimentMetadata):
        return v

    # If it's a string, import it. A path that names no metadata class is a value that does not fit, not a failure
    # of the program, so that the model's validation reports it.
    if isinstance(v, str):
        try:
            return resolve_metadata_class(v)
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"'{v}' is not the path of a metadata class: {error}") from error

    raise ValueError("Must be a class or a valid import path string.")


def get_path_from_class(cls: type[ExperimentMetadata]) -> str:
    """Serializer: Class -> String (Runs when saving JSON)"""
    return f"{cls.__module__}.{cls.__name__}"


# This tells Pydantic to intercept this type in both directions.
MetadataCls = Annotated[
    type[ExperimentMetadata],
    BeforeValidator(resolve_class_from_path),
    PlainSerializer(get_path_from_class, return_type=str, when_used="json"),
]

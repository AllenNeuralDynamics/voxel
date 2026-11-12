"""Experiment metadata models for Voxel sessions."""

import importlib
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode

BASE_METADATA_SCHEMA = "vxl.core.instrument.metadata.ExperimentMetadata"


def annotation(**kwargs: Any) -> Any:
    """Mark a metadata field as an annotation (editable post-acquisition).

    Unmarked fields are provenance by default (locked after first acquisition).
    """
    extra = kwargs.pop("json_schema_extra", None) or {}
    extra["isAnnotation"] = True
    return Field(**kwargs, json_schema_extra=extra)


class ExperimentMetadata(BaseModel):
    """Base class for experiment metadata.

    Subclass to define custom schemas for different instruments or labs.
    Fields are provenance by default — use ``annotation()`` instead of ``Field()``
    for fields that should remain editable after acquisition starts.
    """

    model_config = {"extra": "forbid"}

    notes: str = annotation(default="", description="Experiment notes")

    @classmethod
    def annotation_fields(cls) -> set[str]:
        """Return the set of field names marked as annotations."""
        names: set[str] = set()
        for name, field_info in cls.model_fields.items():
            extra = field_info.json_schema_extra
            if isinstance(extra, dict) and extra.get("isAnnotation"):
                names.add(name)
        return names

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

    # If it's a string, import it
    if isinstance(v, str):
        module_path, class_name = v.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not issubclass(cls, ExperimentMetadata):
            raise TypeError(f"'{v}' is not an ExperimentMetadata subclass")
        return cls

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

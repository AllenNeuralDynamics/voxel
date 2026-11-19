"""Shared model policies and validation helpers for immutable value schemas."""

import re
from collections.abc import Hashable, Iterable, Mapping
from functools import partial
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, ErrorDetails


class FrozenModel(BaseModel):
    """Strict, immutable model with conventional Pydantic serialization."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        frozen=True,
    )


class SparseModel(FrozenModel):
    """Frozen model that omits fields whose value is ``None`` when serialized."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump_json(**kwargs)


class _Key:
    """The type of :data:`Key`. In a JSON Schema the field gets ``"x-key": true``."""

    def __repr__(self) -> str:
        return "Key"

    def __get_pydantic_json_schema__(self, schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        return {**handler(schema), "x-key": True}


Key = _Key()
"""Mark the field that identifies each item of an ordered collection: ``id: Annotated[TaskId, Key]``."""


def key_field(model: type[BaseModel]) -> str:
    """The 1 field of ``model`` marked with :data:`Key`. Raise ``TypeError`` when it has none or more than 1."""
    found = [name for name, info in model.model_fields.items() if Key in info.metadata]
    if len(found) != 1:
        raise TypeError(f"{model.__name__} needs exactly 1 field marked Key, found {found or 'none'}")
    return found[0]


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+")


def check_identifier(value: str, kind: str) -> str:
    """Return ``value`` if it uses only ASCII letters, digits, ``_`` and ``-``; ``kind`` names it in the error.

    Identifiers appear in URLs, file paths and inside other names, so separators and spaces are excluded.
    """
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{kind} '{value}' may use only letters, digits, '_' and '-'")
    return value


def identifier(kind: str) -> AfterValidator:
    """Annotated metadata applying :func:`check_identifier`, as in ``Annotated[str, identifier("Profile id")]``."""
    return AfterValidator(partial(check_identifier, kind=kind))


def error_message(error: ErrorDetails) -> str:
    """The message of 1 pydantic error, with a missing tag of a tagged union said plainly.

    Pydantic's own message for a missing tag names only the field, such as "Unable to extract tag using
    discriminator 'kind'".
    """
    if error["type"] == "union_tag_not_found":
        return f"write {error.get('ctx', {}).get('discriminator', 'the tag')}: it picks 1 of the choices here"
    return error["msg"]


def repeated[T: Hashable](values: Iterable[T]) -> list[T]:
    """Return each value that appears more than once, in the order it first repeats."""
    seen: set[T] = set()
    found: dict[T, None] = {}
    for value in values:
        if value in seen:
            found[value] = None
        seen.add(value)
    return list(found)


def _check_unique[T: Hashable](values: list[T]) -> list[T]:
    if duplicates := repeated(values):
        raise ValueError(f"each item must appear once (repeated: {[str(value) for value in duplicates]})")
    return values


type UniqueList[T] = Annotated[list[T], AfterValidator(_check_unique)]
"""A list where each item appears 1 time."""


def duplicate_keys[K: Hashable](scopes: Mapping[str, Iterable[K]]) -> dict[K, list[str]]:
    """Return each key that appears more than once across ``scopes``, with the scopes that hold it.

    Scopes are named iterables of keys, so mappings can be passed as they are. Scope names keep input order.
    """
    found: dict[K, list[str]] = {}
    for scope, keys in scopes.items():
        for key in keys:
            found.setdefault(key, []).append(scope)
    return {key: names for key, names in found.items() if len(names) > 1}


__all__ = [
    "FrozenModel",
    "Key",
    "SparseModel",
    "UniqueList",
    "check_identifier",
    "duplicate_keys",
    "error_message",
    "identifier",
    "key_field",
    "repeated",
]

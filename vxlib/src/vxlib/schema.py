"""Shared model policies and validation helpers for immutable value schemas."""

import re
from collections.abc import Hashable, Iterable, Mapping
from functools import partial
from typing import Any

from pydantic import AfterValidator, BaseModel, ConfigDict


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


def duplicate_keys[K: Hashable](scopes: Mapping[str, Iterable[K]]) -> dict[K, list[str]]:
    """Return each key that appears more than once across ``scopes``, with the scopes that hold it.

    Scopes are named iterables of keys, so mappings can be passed as they are. Scope names keep input order.
    """
    found: dict[K, list[str]] = {}
    for scope, keys in scopes.items():
        for key in keys:
            found.setdefault(key, []).append(scope)
    return {key: names for key, names in found.items() if len(names) > 1}


__all__ = ["FrozenModel", "SparseModel", "check_identifier", "duplicate_keys", "identifier"]

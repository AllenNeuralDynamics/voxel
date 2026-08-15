"""Shared model policies for immutable value schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict


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


__all__ = ["FrozenModel", "SparseModel"]

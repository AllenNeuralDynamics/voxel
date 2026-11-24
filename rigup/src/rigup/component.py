"""The components that rigup builds: devices and parts."""

from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RigComponent(Protocol):
    """A device or a part. ``id`` is its name in the rig and ``kind`` says what it is; neither changes."""

    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> str: ...


class Part(BaseModel, frozen=True):
    """A component that holds only data, checked when the part is made.

    A plain part gets its ``kind`` from its entry. A class of parts states the kind of all its parts, as a device class
    does: ``class Filter(Part, kind="filter")``. Its entries then need no ``kind``, and one that gives another kind is
    refused. ``details`` holds information for people, such as a vendor or a serial number.
    """

    model_config = ConfigDict(extra="forbid")

    __kind: ClassVar[str] = ""

    id: str
    kind: str = ""
    details: dict[str, Any] = Field(default_factory=dict)

    def __init_subclass__(cls, *, kind: str = "", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if kind:
            cls.__kind = kind

    @model_validator(mode="before")
    @classmethod
    def _take_the_kind_of_the_class(cls, data: Any) -> Any:
        if not cls.__kind or not isinstance(data, Mapping):
            return data
        if data.get("kind", cls.__kind) != cls.__kind:
            raise ValueError(f"a {cls.__name__} is a '{cls.__kind}', not a '{data['kind']}'")
        return {**data, "kind": cls.__kind}

    @model_validator(mode="after")
    def _has_a_kind(self) -> Self:
        if not self.kind:
            raise ValueError("a part needs a kind")
        return self

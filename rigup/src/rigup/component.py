"""The components that rigup builds: devices and parts."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class RigComponent(Protocol):
    """A device or a part. ``id`` is its name in the rig and ``kind`` says what it is; neither changes."""

    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> str: ...


class Part(BaseModel, frozen=True):
    """A component that holds only data, checked when the part is made.

    ``details`` holds information for people, such as a vendor or a serial number.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    details: dict[str, Any] = Field(default_factory=dict)

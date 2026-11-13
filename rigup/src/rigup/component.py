"""What rigup builds: a device or a part."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class RigComponent(Protocol):
    """Anything that rigup builds: a device or a part. ``uid`` is its name in the rig, and ``kind`` says what it is.
    Neither can change."""

    @property
    def uid(self) -> str: ...

    @property
    def kind(self) -> str: ...


class Part(BaseModel, frozen=True):
    """A component with only data. The data is checked when the part is made, and it does not change. ``details``
    holds information for people, such as a vendor or a serial number."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    kind: str
    details: dict[str, Any] = Field(default_factory=dict)

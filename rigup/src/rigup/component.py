"""What rigup builds: a device or a part."""

from typing import Protocol

from pydantic import BaseModel


class RigComponent(Protocol):
    """Anything that rigup builds: a device or a part. ``uid`` is its name in the rig, and ``kind`` says what it is.
    Neither can change."""

    @property
    def uid(self) -> str: ...

    @property
    def kind(self) -> str: ...


class Part(BaseModel, frozen=True):
    """A component with only data. The data is checked when the part is made, and it does not change."""

    uid: str
    kind: str

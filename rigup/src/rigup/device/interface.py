"""The description of a built device that clients read."""

from pydantic import BaseModel, Field

from rigup.interface import OperationInfo, PropInfo, StreamTier


class DeviceInterface(BaseModel):
    """A built device with its controller. ``streaming`` gives the seconds between sends for each stream tier."""

    uid: str
    kind: str
    streaming: dict[StreamTier, float] = Field(default_factory=dict)
    operations: dict[str, OperationInfo] = Field(default_factory=dict)
    props: dict[str, PropInfo] = Field(default_factory=dict)

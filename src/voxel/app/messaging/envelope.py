from pydantic import BaseModel
from typing import Any


class MessageEnvelope(BaseModel):
    topic: str
    subtopic: str | None = None
    payload: Any
    timestamp: int | None = None

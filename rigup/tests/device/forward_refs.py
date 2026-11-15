from __future__ import annotations

import datetime
import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel
from rigup.device import Device, action, integer, query, stream

EPOCH = datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)


class Color(enum.Enum):
    RED = "red"


class FD(Device, kind="fd"):
    def __init__(self):
        super().__init__("fd")
        self.v = 0
        self.calls = []

    @integer(minimum=0, maximum=10, step=2)
    @stream(units=lambda self: self.uid + "-u")
    def count(self) -> int:
        return self.v

    @count.setter
    def count(self, v: int) -> None:
        self.v = v

    @property
    @stream()
    def later(self) -> Later:
        return Later(a=1)

    @query()
    def get_later(self, x: Later, items: list[Later], m: dict[str, Later]) -> Later:
        del items, m
        return x

    @action()
    def misc(
        self,
        p: Path = Path("data"),
        c: Color = Color.RED,
        when: datetime.datetime = EPOCH,
        lit: Literal["a", "b"] = "a",
        raw: bytes = b"",
        td: TD | None = None,
        dc: DC | None = None,
    ) -> None:
        self.calls.append((p, c, when, lit, raw, td, dc))


class Later(BaseModel):
    a: int


class TD(TypedDict):
    k: int


@dataclass
class DC:
    z: float

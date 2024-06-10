from abc import ABC, abstractmethod
import logging
import re
from typing import Literal

from pydantic import BaseModel, model_validator

class FlipMountConfig(BaseModel):
    id: str
    conn: str
    positions: dict[str, Literal[0, 1]]
    init_pos: str
    init_flip_time_ms: int

    @model_validator(mode="after")
    def init_pos_must_be_in_positions(self):
        if self.init_pos not in self.positions:
            raise ValueError(f"init_pos must be one of {self.positions.keys()}")
        return self

class BaseFlipMount(ABC):
    def __init__(self, id: str):
        self.id = id
        self.log = logging.getLogger(__name__ + "." + self.__class__.__name__)

    @abstractmethod
    def connect(self):
        """Connect to the flip mount."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the flip mount."""
        pass

    @property
    @abstractmethod
    def position(self) -> str | None:
        """Position of the flip mount."""
        pass

    @position.setter
    @abstractmethod
    def position(self, position_name: str, wait=False):
        pass

    @abstractmethod
    def toggle(self):
        """Toggle the flip mount position """
        pass

    @property
    @abstractmethod
    def flip_time_ms(self) -> int:
        """Time it takes to flip the mount in milliseconds."""
        pass

    @flip_time_ms.setter
    @abstractmethod
    def flip_time_ms(self, time_ms: int):
        pass

    def __del__(self):
            self.disconnect()

# Path: voxel/devices/flip_mount/thorlabs_mff101.py
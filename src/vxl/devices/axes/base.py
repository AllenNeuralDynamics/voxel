from abc import abstractmethod

from rigup import Device


class Axis[P](Device):
    """A device that moves to a position: a number for a continuous axis, the name of a slot for a discrete axis."""

    @abstractmethod
    def move_to(self, position: P, *, wait: bool = False, timeout_s: float | None = None) -> None:
        """Move to ``position``. With ``wait``, return when the axis is there; ``timeout_s`` bounds that wait."""

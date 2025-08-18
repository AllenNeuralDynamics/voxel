from time import sleep
from collections.abc import Sequence

from voxel_classic.descriptors.deliminated_property import DeliminatedProperty
from voxel_classic.devices.flip_mount.base import BaseFlipMount

# The simulated hardware currently supports two discrete positions (0 / 1).
VALID_POSITIONS: Sequence[int] = (0, 1)
FLIP_TIME_RANGE_MS = (500.0, 2800.0, 100.0)  # min, max, step


class SimulatedFlipMount(BaseFlipMount):
    def __init__(self, uid: str, conn: object, positions: dict[str, int]) -> None:
        super().__init__(uid)
        if not positions:
            raise ValueError("positions mapping must contain at least one entry")
        # Validate values & preserve insertion order for deterministic toggling.
        bad = {k: v for k, v in positions.items() if v not in VALID_POSITIONS}
        if bad:
            raise ValueError(f"Invalid numeric positions {bad}. Allowed numeric values are {list(VALID_POSITIONS)}")
        # Enforce uniqueness of numeric values so we do not have ambiguous reverse lookup.
        if len(set(positions.values())) != len(positions.values()):
            raise ValueError("Duplicate numeric position values are not allowed in simulated flip mount")

        self._conn = conn
        # Internal state containers
        self._positions: dict[str, int] = dict(positions)
        self._order: list[str] = list(self._positions.keys())
        self._current_key: str = self._order[0]  # default first key
        self._flip_time_ms: float = FLIP_TIME_RANGE_MS[0]

    # ------------- Public API -------------
    def close(self) -> None:
        """Close the simulated device (reset to first position)."""
        self._current_key = self._order[0]

    def wait(self) -> None:
        """Simulate mechanical settling time after a movement."""
        sleep(self._flip_time_ms * 1e-3)

    def toggle(self, wait: bool = False) -> None:
        """Cycle to the next defined position (wraps around).

        For the current two-position simulation this simply flips between the two.
        """
        idx = self._order.index(self._current_key)
        self._current_key = self._order[(idx + 1) % len(self._order)]
        if wait:
            self.wait()

    @property
    def position(self) -> str | None:
        """Return the current *name* of the position."""
        return self._current_key

    @position.setter
    def position(self, position_name: str) -> None:
        if position_name not in self._positions:
            raise ValueError(f"Invalid position {position_name}. Valid positions are {list(self._positions.keys())}")
        self._current_key = position_name

    @property
    def numeric_position(self) -> int:
        return self._positions[self._current_key]

    @DeliminatedProperty(minimum=FLIP_TIME_RANGE_MS[0], maximum=FLIP_TIME_RANGE_MS[1], step=FLIP_TIME_RANGE_MS[2])
    def flip_time_ms(self) -> float:
        return self._flip_time_ms

    @flip_time_ms.setter
    def flip_time_ms(self, time_ms: float) -> None:
        self.log.info(f"Setting flip_time_ms to {time_ms}")
        self._flip_time_ms = time_ms

    # ------------- Introspection / helpers -------------
    def available_positions(self) -> list[str]:
        """List available position *names* (in toggle order)."""
        return list(self._order)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"SimulatedFlipMount(id={self.uid!r}, position={self.position!r}, "
            f"numeric={self.numeric_position}, flip_time_ms={self.flip_time_ms})"
        )

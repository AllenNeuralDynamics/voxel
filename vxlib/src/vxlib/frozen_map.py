"""An immutable, hashable mapping."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, final


@final
class FrozenMap[K, V](Mapping[K, V]):
    """An immutable mapping. It copies its input when made, so no outside dict can change it. It is hashable when
    its values are."""

    __slots__ = ("_hash", "_items")

    _items: dict[K, V]
    _hash: int | None

    def __init__(self, items: Mapping[K, V] | Iterable[tuple[K, V]] = (), /) -> None:
        self._items = dict(items)
        self._hash = None

    def __getitem__(self, key: K) -> V:
        return self._items[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(frozenset(self._items.items()))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenMap):
            return self._items == other._items
        return NotImplemented

    def __repr__(self) -> str:
        return f"FrozenMap({self._items!r})"

    def __reduce__(self) -> tuple[Any, ...]:
        return (FrozenMap, (self._items,))


__all__ = ["FrozenMap"]

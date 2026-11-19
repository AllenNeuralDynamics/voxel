import copy
from typing import Any, cast

import pytest
from vxlib.frozen_map import FrozenMap


def test_a_frozen_map_keeps_its_own_copy() -> None:
    source = {"wheel": "gfp"}
    frozen = FrozenMap(source)
    source["wheel"] = "rfp"

    assert frozen["wheel"] == "gfp"


def test_a_frozen_map_refuses_writes() -> None:
    with pytest.raises(TypeError):
        cast("Any", FrozenMap({"wheel": "gfp"}))["wheel"] = "rfp"


def test_equal_frozen_maps_hash_the_same_and_differ_from_a_dict() -> None:
    first, second = FrozenMap({"a": 1, "b": 2}), FrozenMap([("b", 2), ("a", 1)])

    assert first == second
    assert hash(first) == hash(second)
    assert first != {"a": 1, "b": 2}


def test_a_frozen_map_with_an_unhashable_value_cannot_be_hashed() -> None:
    with pytest.raises(TypeError):
        hash(FrozenMap({"a": [1]}))


def test_a_frozen_map_reads_and_copies_like_a_mapping() -> None:
    frozen = FrozenMap({"a": 1})

    assert (list(frozen), len(frozen), frozen.get("b"), dict(frozen)) == (["a"], 1, None, {"a": 1})
    assert copy.deepcopy(frozen) == frozen

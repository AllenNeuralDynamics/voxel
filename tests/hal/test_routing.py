import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest

from rigup import Result
from vxl.hal.core import RouteDimension
from vxl.hal.errors import HALError
from vxl.hal.topology import OpticalRouteDefinition

if TYPE_CHECKING:
    from vxl.devices.axes.discrete.handle import DiscreteAxisHandle


def _selector(label, moving):
    props = {
        "label": Result.ok(SimpleNamespace(value=label)),
        "is_moving": Result.ok(SimpleNamespace(value=moving)),
    }
    return SimpleNamespace(props=SimpleNamespace(get=AsyncMock(return_value=props)))


@pytest.mark.parametrize(
    ("label", "moving", "expected"),
    [("left", False, "left"), ("left", True, None), ("left", None, None), (None, False, None), ("right", False, None)],
)
async def test_current_route_reads_all_selectors_and_requires_a_unique_stationary_match(
    label, moving, expected
) -> None:
    routes = {
        "left": OpticalRouteDefinition({"a": "left", "b": "left"}),
        "right": OpticalRouteDefinition({"a": "right", "b": "right"}),
    }
    dimension = RouteDimension(
        uid="side",
        selectors={
            "a": cast("DiscreteAxisHandle", _selector("left", False)),
            "b": cast("DiscreteAxisHandle", _selector(label, moving)),
        },
        _definitions=routes,
    )
    assert await dimension.current_route() == expected
    if expected is not None:
        assert await replace(dimension, _definitions={**routes, "alias": routes[expected]}).current_route() is None


async def test_selection_waits_for_all_failures_and_identifies_the_selectors() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_failure(*_args, **_kwargs) -> None:
        entered.set()
        await release.wait()
        raise RuntimeError("second failure")

    dimension = RouteDimension(
        uid="side",
        selectors={
            "a": cast("DiscreteAxisHandle", SimpleNamespace(select=AsyncMock(side_effect=ValueError("first failure")))),
            "b": cast("DiscreteAxisHandle", SimpleNamespace(select=AsyncMock(side_effect=delayed_failure))),
        },
        _definitions={"left": OpticalRouteDefinition({"a": "left", "b": "left"})},
    )
    selection = asyncio.create_task(dimension.select("left"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert not selection.done()
    finally:
        release.set()
        with pytest.raises(ExceptionGroup) as caught:
            await asyncio.wait_for(selection, timeout=1)
    errors = caught.value.exceptions
    assert [str(error) for error in errors] == ["first failure", "second failure"]
    assert errors[0].__notes__ == ["Routing dimension 'side', selector 'a'"]
    assert errors[1].__notes__ == ["Routing dimension 'side', selector 'b'"]


async def test_selection_preserves_cancellation() -> None:
    dimension = RouteDimension(
        uid="side",
        selectors={
            "a": cast("DiscreteAxisHandle", SimpleNamespace(select=AsyncMock(side_effect=asyncio.CancelledError))),
        },
        _definitions={"left": OpticalRouteDefinition({"a": "left"})},
    )
    with pytest.raises(asyncio.CancelledError):
        await dimension.select("left")


async def test_unknown_route_is_rejected_without_moving_selectors() -> None:
    select = AsyncMock()
    dimension = RouteDimension(
        uid="side",
        selectors={"a": cast("DiscreteAxisHandle", SimpleNamespace(select=select))},
        _definitions={"left": OpticalRouteDefinition({"a": "left"})},
    )
    with pytest.raises(HALError, match=r"No optical route 'side\.missing'"):
        await dimension.select("missing")
    select.assert_not_called()

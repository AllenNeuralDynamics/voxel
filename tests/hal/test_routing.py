import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest

from rigup import Result
from vxl.devices.axes.discrete.base import DiscreteAxisState
from vxl.hal.core import RouteDimension
from vxl.hal.errors import HALError
from vxl.hal.topology import OpticalRouteDefinition

if TYPE_CHECKING:
    from vxl.devices.axes.discrete.handle import DiscreteAxisHandle


def _selector(position, moving, *, target=0):
    props = {
        "state": Result.ok(
            SimpleNamespace(value=DiscreteAxisState(position=position, target=target, is_moving=moving).model_dump())
        ),
        "labels": Result.ok(SimpleNamespace(value={"0": "left", "1": "right", "2": None})),
    }
    return SimpleNamespace(props=SimpleNamespace(get=AsyncMock(return_value=props)))


@pytest.mark.parametrize(
    ("position", "moving", "expected"),
    [(0, False, "left"), (0, True, None), (None, False, None), (2, False, None), (1, False, None)],
)
async def test_current_route_reads_all_selectors_and_requires_a_unique_stationary_match(
    position, moving, expected
) -> None:
    routes = {
        "left": OpticalRouteDefinition(selectors={"a": "left", "b": "left"}),
        "right": OpticalRouteDefinition(selectors={"a": "right", "b": "right"}),
    }
    dimension = RouteDimension(
        uid="side",
        selectors={
            "a": cast("DiscreteAxisHandle", _selector(0, False)),
            "b": cast("DiscreteAxisHandle", _selector(position, moving)),
        },
        _definitions=routes,
    )
    assert await dimension.current_route() == expected
    if expected is not None:
        assert await replace(dimension, _definitions={**routes, "alias": routes[expected]}).current_route() is None


async def test_selection_requires_feedback_even_when_target_matches() -> None:
    selector = _selector(None, False, target=0)
    selector.select = AsyncMock()
    dimension = RouteDimension(
        uid="side",
        selectors={"a": cast("DiscreteAxisHandle", selector)},
        _definitions={"left": OpticalRouteDefinition(selectors={"a": "left"})},
    )
    with pytest.raises(ExceptionGroup) as caught:
        await dimension.select("left")
    assert isinstance(caught.value.exceptions[0], HALError)
    assert "settled label is None" in str(caught.value.exceptions[0])


async def test_current_route_propagates_read_failure() -> None:
    selector = _selector(0, False)
    selector.props.get.side_effect = RuntimeError("connection lost")
    dimension = RouteDimension(
        uid="side",
        selectors={"a": cast("DiscreteAxisHandle", selector)},
        _definitions={"left": OpticalRouteDefinition(selectors={"a": "left"})},
    )
    with pytest.raises(RuntimeError, match="connection lost"):
        await dimension.current_route()


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
        _definitions={"left": OpticalRouteDefinition(selectors={"a": "left", "b": "left"})},
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
        _definitions={"left": OpticalRouteDefinition(selectors={"a": "left"})},
    )
    with pytest.raises(asyncio.CancelledError):
        await dimension.select("left")


async def test_unknown_route_is_rejected_without_moving_selectors() -> None:
    select = AsyncMock()
    dimension = RouteDimension(
        uid="side",
        selectors={"a": cast("DiscreteAxisHandle", SimpleNamespace(select=select))},
        _definitions={"left": OpticalRouteDefinition(selectors={"a": "left"})},
    )
    with pytest.raises(HALError, match=r"No optical route 'side\.missing'"):
        await dimension.select("missing")
    select.assert_not_called()

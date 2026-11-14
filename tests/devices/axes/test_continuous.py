from collections.abc import Awaitable, Callable

import pytest
from rigup.config import DeviceConfig
from rigup.node import LocalNode
from vxlib.vector import Span

from vxl.devices.axes.continuous.base import ContinuousAxisNewController, Pulses, Sweep
from vxl.devices.axes.continuous.linear import LinearAxisController, LinearAxisHandle
from vxl.devices.axes.continuous.rotation import RotationAxisController, RotationAxisHandle
from vxl.devices.axes.continuous.simulated import SimulatedLinearAxis, SimulatedRotationAxis

_SIMULATED = "vxl.devices.axes.continuous.simulated"

type Call = Callable[[ContinuousAxisNewController], Awaitable[object]]


async def test_each_kind_shows_its_unit_and_limits_across_a_rig_node() -> None:
    node = LocalNode(node_id="test")
    configs = {
        "z": DeviceConfig(target=f"{_SIMULATED}.SimulatedLinearAxis", init={"lower": -100, "upper": 1000}),
        "r": DeviceConfig(target=f"{_SIMULATED}.SimulatedRotationAxis", init={}),
    }
    handles, errors = await node.build_devices(configs)
    assert errors == {}
    z, r = LinearAxisHandle.wrap(handles["z"]), RotationAxisHandle.wrap(handles["r"])
    try:
        for handle, unit in ((z, "µm"), (r, "deg")):
            properties = (await handle.interface()).properties
            units = [properties[name].units for name in ("position", "limits", "speed", "acceleration")]
            assert units == [unit, unit, f"{unit}/s", f"{unit}/s²"]
        assert await z.get_limits() == Span(-100, 1000)
        assert await r.get_limits() is None
    finally:
        await node.close()


def _linear() -> LinearAxisController:
    return LinearAxisController(SimulatedLinearAxis("z", lower=0, upper=100, speed=50_000))


def _free_rotation() -> RotationAxisController:
    return RotationAxisController(SimulatedRotationAxis("r", speed=3_600))


def _limited_rotation() -> RotationAxisController:
    return RotationAxisController(SimulatedRotationAxis("r", lower=-180, upper=180, speed=3_600))


@pytest.mark.parametrize(
    ("make", "call", "refused"),
    [
        (_linear, lambda axis: axis.move_to(150), True),
        (_linear, lambda axis: axis.move_to(50), False),
        (_free_rotation, lambda axis: axis.move_to(3_600), False),
        (_limited_rotation, lambda axis: axis.move_to(270), True),
        (_limited_rotation, lambda axis: axis.sweep(Sweep(first=-90, last=90, speed=1_440)), True),
        (_limited_rotation, lambda axis: axis.sweep(Sweep(first=-90, last=90, speed=90)), False),
    ],
    ids=[
        "linear past its limits",
        "linear inside its limits",
        "rotation with no limits, 10 turns",
        "rotation past its limits",
        "rotation whose run-up passes its limits",
        "rotation whose run-up fits",
    ],
)
async def test_each_kind_keeps_moves_and_scans_inside_its_limits(
    make: Callable[[], ContinuousAxisNewController], call: Call, refused: bool
) -> None:
    axis = make()
    if refused:
        with pytest.raises(ValueError, match="cannot reach"):
            await call(axis)
    else:
        await call(axis)


class _Faulty(SimulatedLinearAxis):
    @property
    def fault(self) -> str | None:
        return "not homed"


async def _stepping() -> LinearAxisController:
    axis = _linear()
    await axis.arm_steps(5.0, 3, "ttl_in")
    return axis


async def _faulty() -> LinearAxisController:
    return LinearAxisController(_Faulty("z", lower=0, upper=100))


async def _idle() -> LinearAxisController:
    return _linear()


@pytest.mark.parametrize(
    ("make", "call", "error"),
    [
        (_stepping, lambda axis: axis.move_to(50), "while stepping"),
        (_faulty, lambda axis: axis.move_to(50), "not homed"),
        (_idle, lambda axis: axis.sweep(Sweep(first=10, last=20, speed=1e6)), "cannot hold a speed"),
        (_idle, lambda axis: axis.sweep(Sweep(first=10, last=20, speed=0.5)), "cannot hold a speed"),
    ],
    ids=["a move while stepping", "a move with a fault", "a sweep too fast", "a sweep too slow"],
)
async def test_an_axis_refuses_unsafe_requests(
    make: Callable[[], Awaitable[LinearAxisController]], call: Call, error: str
) -> None:
    axis = await make()
    with pytest.raises((RuntimeError, ValueError), match=error):
        await call(axis)


@pytest.mark.parametrize(
    ("first", "last", "positions"),
    [(0, 100, [0, 25, 50, 75, 100]), (20, 0, [20, 15, 10, 5, 0])],
    ids=["forwards", "backwards"],
)
def test_pulses_fall_from_first_to_last(first: float, last: float, positions: list[float]) -> None:
    sweep = Sweep(first=first, last=last, speed=10, pulses=Pulses(count=5, pin="ttl_out"))
    assert sweep.pulse_positions == positions

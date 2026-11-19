"""The node monitor reports the process of its node and the machine it runs on."""

from collections.abc import AsyncIterator

import pytest
from rigup.config import RigConfig
from rigup.device import StreamTier
from rigup.rig import Rig

from vxl.devices.node import NodeMonitor, NodeMonitorHandle
from vxl.system import System

_MONITOR = {"target": "vxl.devices.node.NodeMonitor"}
_CAMERA = {"target": "vxl.devices.camera.simulated.SimulatedCamera"}


@pytest.fixture
async def rig() -> AsyncIterator[Rig]:
    """A rig with a monitor in this process, and a monitor and a camera on a node of its own."""
    config = RigConfig.model_validate(
        {
            "devices": {"monitor": _MONITOR},
            "nodes": {"cam_node": {"devices": {"cam_monitor": _MONITOR, "camera": _CAMERA}}},
        }
    )
    rig = Rig(config, name="test")
    await rig.open()
    yield rig
    await rig.close()


async def test_each_monitor_reports_its_own_process_and_the_shared_machine(rig: Rig) -> None:
    assert rig.build_errors == {}
    here, there = (NodeMonitorHandle.wrap(rig.devices[uid]) for uid in ("monitor", "cam_monitor"))

    assert (await here.interface()).kind == "node_monitor"
    assert (await here.interface()).operations == {}
    assert here.pid.value != there.pid.value
    assert here.hostname.value == there.hostname.value == System.hostname()
    assert here.cpu_count.value == there.cpu_count.value


async def test_a_monitor_lists_the_processes_of_its_machine_and_their_claims(rig: Rig) -> None:
    monitor = NodeMonitorHandle.wrap(rig.devices["monitor"])

    listed = {entry.name: entry.claims for entry in await monitor.processes.get()}

    assert listed == {"monitor": {}, "cam_monitor": {"ram": {"camera": 1.0}}}


@pytest.mark.parametrize(("streaming", "interval"), [(None, 60.0), ({"slow": 5.0}, 5.0)])
async def test_the_slow_streams_poll_once_a_minute_unless_the_rig_says_otherwise(
    streaming: dict[StreamTier, float] | None, interval: float
) -> None:
    controller = NodeMonitor("monitor").make_controller(streaming=streaming)
    try:
        assert controller.streaming["slow"] == interval
    finally:
        await controller.close()

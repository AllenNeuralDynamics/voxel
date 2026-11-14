import os
import sys
import time
from collections.abc import AsyncIterator

import pytest
from rigup.config import DeviceConfig, NodeConfig
from rigup.node import SubprocessNode
from rigup.node._protocol import Action, PingPayload, call

pytestmark = pytest.mark.slow


@pytest.fixture
async def node(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SubprocessNode]:
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(path for path in sys.path if path))
    node = SubprocessNode("child", NodeConfig(kind="subprocess"))
    await node.open()
    try:
        yield node
    finally:
        await node.close()


async def test_a_subprocess_node_runs_device_commands(node: SubprocessNode) -> None:
    handles, _ = await node.build_devices({"dev": DeviceConfig(target="rigup_fakes.MockDevice")})

    result = await handles["dev"].call("add", a=2.0, b=3.0)

    assert result == 5.0


async def test_a_killed_node_process_fails_pending_calls_at_once(node: SubprocessNode) -> None:
    assert node._process is not None
    node._process.kill()

    began = time.monotonic()
    with pytest.raises(ConnectionError):
        await call(node.transport, Action.PING, PingPayload(), PingPayload, timeout_s=30.0)

    assert time.monotonic() - began < 2.0

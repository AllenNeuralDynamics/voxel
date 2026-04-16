"""Tests for LocalNode + LocalAdapter — full in-process device path."""

import pytest
from rigup.config import DeviceConfig
from rigup.node import LocalNode

MOCK_TARGET = "tests._mock.MockDevice"


@pytest.fixture
def node() -> LocalNode:
    return LocalNode(node_id="test-local")


@pytest.fixture
def device_configs() -> dict[str, DeviceConfig]:
    return {
        "dev_a": DeviceConfig(target=MOCK_TARGET, init={"initial_value": 1.0}),
        "dev_b": DeviceConfig(target=MOCK_TARGET, init={"initial_value": 2.0}),
    }


class TestLocalNodeBuild:
    async def test_build_creates_handles(self, node: LocalNode, device_configs):
        handles, errors = await node.build_devices(device_configs)
        assert len(handles) == 2
        assert not errors
        assert "dev_a" in node.devices
        assert "dev_b" in node.devices
        await node.close()

    async def test_build_is_declarative(self, node: LocalNode):
        configs_1 = {"dev_1": DeviceConfig(target=MOCK_TARGET, init={})}
        configs_2 = {"dev_2": DeviceConfig(target=MOCK_TARGET, init={})}

        await node.build_devices(configs_1)
        assert "dev_1" in node.devices

        await node.build_devices(configs_2)
        assert "dev_1" not in node.devices
        assert "dev_2" in node.devices
        await node.close()

    async def test_build_with_bad_target(self, node: LocalNode):
        configs = {"bad": DeviceConfig(target="nonexistent.Module", init={})}
        handles, errors = await node.build_devices(configs)
        assert not handles
        assert "bad" in errors
        await node.close()


class TestLocalNodeDeviceOps:
    async def test_run_command(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        handle = node.devices["dev_a"]

        result = await handle.call("set_value", v=42.0)
        assert result == 42.0
        await node.close()

    async def test_get_set_props(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        handle = node.devices["dev_a"]

        props = await handle.get_props("value")
        assert props["value"].unwrap().value == 1.0

        await handle.set_prop("value", 99.0)
        props = await handle.get_props("value")
        assert props["value"].unwrap().value == 99.0
        await node.close()

    async def test_command_error(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        handle = node.devices["dev_a"]

        result = await handle.run_command("fail")
        assert not result.is_ok
        await node.close()

    async def test_interface(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        handle = node.devices["dev_a"]

        iface = await handle.interface()
        assert iface.type == "mock"
        assert "set_value" in iface.commands
        assert "value" in iface.properties
        await node.close()


class TestLocalNodeLifecycle:
    async def test_close_device(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        assert len(node.devices) == 2

        await node.close_device("dev_a")
        assert len(node.devices) == 1
        assert "dev_a" not in node.devices

        await node.close()

    async def test_close_all_devices(self, node: LocalNode, device_configs):
        await node.build_devices(device_configs)
        assert len(node.devices) == 2

        await node.close_all_devices()
        assert len(node.devices) == 0

    async def test_close_nonexistent_device_is_noop(self, node: LocalNode):
        await node.close_device("nonexistent")

    async def test_open_is_noop(self, node: LocalNode):
        await node.open()

"""Tests for Rig — end-to-end with local-only config."""

from rigup.rig import Rig

from rigup import DeviceConfig, RigConfig

MOCK_TARGET = "tests._mock.MockDevice"


def _dev(initial_value: float = 0.0) -> DeviceConfig:
    return DeviceConfig(target=MOCK_TARGET, init={"initial_value": initial_value})


def _bad_dev() -> DeviceConfig:
    return DeviceConfig(target="nonexistent.Module", init={})


class TestRig:
    async def test_open_creates_devices(self):
        config = RigConfig(devices={"dev_a": _dev(1.0), "dev_b": _dev(2.0)})
        rig = Rig(config, name="test-rig")
        await rig.open()
        try:
            assert len(rig.devices) == 2
            assert "dev_a" in rig.devices
            assert "dev_b" in rig.devices
        finally:
            await rig.close()

    async def test_device_commands_work(self):
        config = RigConfig(devices={"dev": _dev()})
        rig = Rig(config, name="test-rig")
        await rig.open()
        try:
            result = await rig.devices["dev"].call("set_value", v=42.0)
            assert result == 42.0
        finally:
            await rig.close()

    async def test_close_clears_state(self):
        config = RigConfig(devices={"dev": _dev()})
        rig = Rig(config, name="test-rig")
        await rig.open()
        assert len(rig.devices) == 1

        await rig.close()
        assert len(rig.devices) == 0
        assert len(rig.nodes) == 0

    async def test_build_errors_captured(self):
        config = RigConfig(devices={"good": _dev(), "bad": _bad_dev()})
        rig = Rig(config, name="test-rig")
        await rig.open()
        try:
            assert "good" in rig.devices
            assert "bad" not in rig.devices
            assert "bad" in rig.build_errors
        finally:
            await rig.close()

    async def test_empty_config(self):
        config = RigConfig()
        rig = Rig(config, name="empty")
        await rig.open()
        assert len(rig.devices) == 0
        assert len(rig.nodes) == 0
        await rig.close()

    async def test_rig_name(self):
        config = RigConfig()
        rig = Rig(config, name="test-rig")
        assert rig.name == "test-rig"

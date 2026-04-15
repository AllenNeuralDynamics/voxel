"""Tests for Rig — end-to-end with local-only config."""

from rigur.config import RigConfig
from rigur.rig import Rig

MOCK_TARGET = "tests._mock.MockDevice"


class TestRig:
    async def test_open_creates_devices(self):
        config = RigConfig(
            name="test",
            devices={
                "dev_a": {"target": MOCK_TARGET, "init": {"initial_value": 1.0}},
                "dev_b": {"target": MOCK_TARGET, "init": {"initial_value": 2.0}},
            },
        )
        rig = Rig(config)
        await rig.open()
        try:
            assert len(rig.devices) == 2
            assert "dev_a" in rig.devices
            assert "dev_b" in rig.devices
        finally:
            await rig.close()

    async def test_device_commands_work(self):
        config = RigConfig(
            name="test",
            devices={"dev": {"target": MOCK_TARGET, "init": {}}},
        )
        rig = Rig(config)
        await rig.open()
        try:
            result = await rig.devices["dev"].call("set_value", v=42.0)
            assert result == 42.0
        finally:
            await rig.close()

    async def test_close_clears_state(self):
        config = RigConfig(
            name="test",
            devices={"dev": {"target": MOCK_TARGET, "init": {}}},
        )
        rig = Rig(config)
        await rig.open()
        assert len(rig.devices) == 1

        await rig.close()
        assert len(rig.devices) == 0
        assert len(rig.nodes) == 0

    async def test_build_errors_captured(self):
        config = RigConfig(
            name="test",
            devices={
                "good": {"target": MOCK_TARGET, "init": {}},
                "bad": {"target": "nonexistent.Module", "init": {}},
            },
        )
        rig = Rig(config)
        await rig.open()
        try:
            assert "good" in rig.devices
            assert "bad" not in rig.devices
            assert "bad" in rig.build_errors
        finally:
            await rig.close()

    async def test_empty_config(self):
        config = RigConfig(name="empty")
        rig = Rig(config)
        await rig.open()
        assert len(rig.devices) == 0
        assert len(rig.nodes) == 0
        await rig.close()

    async def test_rig_name(self):
        config = RigConfig(name="my-rig")
        rig = Rig(config)
        assert rig.name == "my-rig"

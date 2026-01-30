#!/usr/bin/env python
"""Manual test script for distributed rig functionality.

Run with: uv run python tests/test_distributed_manual.py

This script tests the full distributed stack:
- ClusterManager spawning local node subprocesses
- ZMQ communication between rig and nodes
- Device provisioning and command execution

Not run as part of pytest because subprocess management can hang.
"""

import asyncio
import sys
import traceback
from typing import ClassVar

import zmq.asyncio
from rigup.device import describe

from rigup import Device, Rig, RigConfig


class MockLaser(Device):
    """A mock laser device for testing."""

    __DEVICE_TYPE__ = "laser"
    __COMMANDS__: ClassVar[set[str]] = {"enable", "disable"}

    def __init__(self, uid: str, max_power: float = 100.0):
        super().__init__(uid=uid)
        self._power: float = 0.0
        self._max_power = max_power
        self._enabled = False

    @property
    @describe(label="Power", desc="Current power level", units="mW")
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        if value < 0:
            raise ValueError("Power cannot be negative")
        if value > self._max_power:
            raise ValueError(f"Power cannot exceed {self._max_power}")
        self._power = value

    @property
    @describe(label="Enabled", desc="Whether laser is enabled")
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> str:
        if self._power <= 0:
            raise ValueError("Cannot enable laser with zero power")
        self._enabled = True
        return f"Laser enabled at {self._power}mW"

    def disable(self) -> str:
        self._enabled = False
        return "Laser disabled"


async def test_distributed_rig():
    """Test the full distributed rig lifecycle."""
    print("=" * 60)
    print("Testing Distributed Rig")
    print("=" * 60)

    config = RigConfig.model_validate(
        {
            "info": {"name": "test-distributed-rig"},
            "cluster": {"control_port": 19500, "log_port": 19501},
            "nodes": {
                "node_1": {
                    "hostname": "localhost",
                    "devices": {
                        "laser_1": {
                            "target": "tests.test_distributed_manual.MockLaser",
                            "kwargs": {"max_power": 100.0},
                        },
                    },
                },
            },
        },
    )

    zctx = zmq.asyncio.Context()
    rig = None

    try:
        print("\n1. Creating rig...")
        rig = Rig(config, zctx=zctx)

        print("2. Starting rig (spawning nodes)...")
        await rig.start(connection_timeout=10.0, provision_timeout=10.0)
        print(f"   ✓ Rig started with {len(rig.handles)} handles")

        print("\n3. Testing device handle...")
        laser = rig.get_handle("laser_1")

        interface = await laser.interface()
        print(f"   ✓ Got interface: type={interface.type}, commands={list(interface.commands.keys())}")

        print("\n4. Testing property get/set...")
        power = await laser.get_prop_value("power")
        print(f"   Initial power: {power}")

        await laser.set_prop("power", 50.0)
        power = await laser.get_prop_value("power")
        print(f"   ✓ Set power to: {power}")

        print("\n5. Testing command execution...")
        result = await laser.call("enable")
        print(f"   ✓ Enable result: {result}")

        enabled = await laser.get_prop_value("enabled")
        print(f"   ✓ Enabled state: {enabled}")

        result = await laser.call("disable")
        print(f"   ✓ Disable result: {result}")

        print("\n6. Verifying remote device...")
        device = rig.get_device("laser_1")
        assert device is None, "Remote device should return None"
        print("   ✓ get_device() correctly returns None for remote devices")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        traceback.print_exc()
        return False

    finally:
        print("\n7. Stopping rig...")
        if rig:
            await rig.stop()
            print("   ✓ Rig stopped")

        print("8. Terminating ZMQ context...")
        zctx.term()
        print("   ✓ Context terminated")


def main():
    success = asyncio.run(test_distributed_rig())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

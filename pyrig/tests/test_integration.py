"""Integration tests for pyrig - tests the full stack from Rig to Device."""

import asyncio
from enum import StrEnum
from typing import ClassVar

import pytest
from pyrig.device import DeviceController, describe

from pyrig import Device, LocalAdapter, Rig, RigConfig

# ============== Test Devices ==============


class LaserState(StrEnum):
    OFF = "off"
    ON = "on"
    STANDBY = "standby"


class MockLaser(Device[LaserState]):
    """A mock laser device for testing."""

    __DEVICE_TYPE__ = "laser"
    __COMMANDS__: ClassVar[set[str]] = {"enable", "disable"}

    def __init__(self, uid: str, max_power: float = 100.0):
        super().__init__(uid=uid)
        self._power: float = 0.0
        self._max_power = max_power
        self._state = LaserState.OFF

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
    @describe(label="State", desc="Current laser state")
    def state(self) -> LaserState:
        return self._state

    @property
    @describe(label="Max Power", desc="Maximum power limit", units="mW")
    def max_power(self) -> float:
        return self._max_power

    def enable(self) -> str:
        """Enable the laser."""
        if self._power <= 0:
            raise ValueError("Cannot enable laser with zero power")
        self._state = LaserState.ON
        return f"Laser enabled at {self._power}mW"

    def disable(self) -> str:
        """Disable the laser."""
        self._state = LaserState.OFF
        return "Laser disabled"

    @describe(label="Set Power And Enable", desc="Set power and enable in one call")
    def set_power_and_enable(self, power: float) -> str:
        """Set power and enable the laser."""
        self.power = power
        return self.enable()


class StreamingLaser(Device):
    """A laser device with streaming properties for testing subscriptions."""

    __DEVICE_TYPE__ = "laser"

    def __init__(self, uid: str):
        super().__init__(uid=uid)
        self._power: float = 0.0

    @property
    @describe(label="Power", desc="Current power level", units="mW", stream=True)
    def power(self) -> float:
        return self._power

    @power.setter
    def power(self, value: float) -> None:
        self._power = value


class MockCamera(Device):
    """A mock camera device for testing."""

    __DEVICE_TYPE__ = "camera"
    __COMMANDS__: ClassVar[set[str]] = {"capture"}

    def __init__(self, uid: str, resolution: tuple[int, int] = (1920, 1080)):
        super().__init__(uid=uid)
        self._resolution = resolution
        self._exposure_ms: float = 10.0
        self._frame_count = 0

    @property
    @describe(label="Exposure", desc="Exposure time", units="ms")
    def exposure_ms(self) -> float:
        return self._exposure_ms

    @exposure_ms.setter
    def exposure_ms(self, value: float) -> None:
        if value <= 0:
            raise ValueError("Exposure must be positive")
        self._exposure_ms = value

    @property
    @describe(label="Resolution", desc="Camera resolution")
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    @property
    @describe(label="Frame Count", desc="Total frames captured")
    def frame_count(self) -> int:
        return self._frame_count

    def capture(self) -> dict:
        """Capture a frame."""
        self._frame_count += 1
        return {
            "frame_id": self._frame_count,
            "exposure_ms": self._exposure_ms,
            "resolution": self._resolution,
        }

    @describe(label="Capture Sequence", desc="Capture multiple frames")
    def capture_sequence(self, count: int, _interval_ms: float = 0.0) -> list[dict]:
        """Capture a sequence of frames."""
        frames = []
        for _ in range(count):
            frames.append(self.capture())
        return frames


# ============== Tests ==============


class TestLocalRig:
    """Test Rig with local devices (no networking)."""

    @pytest.fixture
    def local_config(self) -> RigConfig:
        """Create a config with local devices only."""
        return RigConfig.model_validate(
            {
                "info": {"name": "test-rig"},
                "devices": {
                    "laser_1": {
                        "target": "tests.test_integration.MockLaser",
                        "init": {"max_power": 50.0},
                    },
                    "camera_1": {
                        "target": "tests.test_integration.MockCamera",
                        "init": {"resolution": [640, 480]},
                    },
                },
            },
        )

    @pytest.mark.asyncio
    async def test_rig_starts_with_local_devices(self, local_config: RigConfig):
        """Test that rig starts and creates handles for local devices."""
        rig = Rig(local_config)
        await rig.start()

        try:
            assert len(rig.handles) == 2
            assert "laser_1" in rig.handles
            assert "camera_1" in rig.handles
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_device_handle_call(self, local_config: RigConfig):
        """Test calling commands through DeviceHandle."""
        rig = Rig(local_config)
        await rig.start()

        try:
            laser = rig.get_handle("laser_1")

            # Set power and enable
            result = await laser.call("set_power_and_enable", 25.0)
            assert "enabled" in result.lower()
            assert "25" in result

            # Check state changed
            state = await laser.get_prop_value("state")
            assert state.lower() == "on"
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_device_handle_properties(self, local_config: RigConfig):
        """Test getting and setting properties through DeviceHandle."""
        rig = Rig(local_config)
        await rig.start()

        try:
            camera = rig.get_handle("camera_1")

            # Get initial exposure
            exposure = await camera.get_prop_value("exposure_ms")
            assert exposure == 10.0

            # Set new exposure
            await camera.set_prop("exposure_ms", 50.0)
            new_exposure = await camera.get_prop_value("exposure_ms")
            assert new_exposure == 50.0

            # Get resolution (read-only)
            resolution = await camera.get_prop_value("resolution")
            assert resolution == [640, 480]
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_device_handle_interface(self, local_config: RigConfig):
        """Test getting device interface metadata."""
        rig = Rig(local_config)
        await rig.start()

        try:
            laser = rig.get_handle("laser_1")
            interface = await laser.interface()

            assert interface.uid == "laser_1"
            assert interface.type == "laser"

            # Check commands
            assert "enable" in interface.commands
            assert "disable" in interface.commands
            assert "set_power_and_enable" in interface.commands

            # Check properties
            assert "power" in interface.properties
            assert "state" in interface.properties
            assert interface.properties["power"].units == "mW"
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_device_handle_error_handling(self, local_config: RigConfig):
        """Test that errors are properly propagated."""
        rig = Rig(local_config)
        await rig.start()

        try:
            laser = rig.get_handle("laser_1")

            # Try to enable with zero power - should fail
            with pytest.raises(RuntimeError, match="zero power"):
                await laser.call("enable")

            # Try to set negative power
            with pytest.raises(RuntimeError, match="negative"):
                await laser.set_prop("power", -10.0)
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_get_device_returns_local_device(self, local_config: RigConfig):
        """Test that get_device returns the actual device instance for local devices."""
        rig = Rig(local_config)
        await rig.start()

        try:
            device = rig.get_device("laser_1")
            assert device is not None
            assert isinstance(device, MockLaser)
            assert device.max_power == 50.0
        finally:
            await rig.stop()

    @pytest.mark.asyncio
    async def test_multiple_device_operations(self, local_config: RigConfig):
        """Test operating on multiple devices."""
        rig = Rig(local_config)
        await rig.start()

        try:
            laser = rig.get_handle("laser_1")
            camera = rig.get_handle("camera_1")

            # Configure laser
            await laser.set_prop("power", 30.0)
            await laser.call("enable")

            # Capture with camera
            frame = await camera.call("capture")
            assert frame["frame_id"] == 1

            # Capture sequence
            frames = await camera.call("capture_sequence", 3)
            assert len(frames) == 3
            assert frames[0]["frame_id"] == 2

            # Check frame count
            count = await camera.get_prop_value("frame_count")
            assert count == 4
        finally:
            await rig.stop()


class TestDeviceController:
    """Test DeviceController directly."""

    @pytest.mark.asyncio
    async def test_ctrl_execute_command(self):
        """Test executing commands through controller."""
        laser = MockLaser("test_laser", max_power=100.0)
        ctrl = DeviceController(laser)

        try:
            # Set power first
            await ctrl.set_props(power=50.0)

            # Execute enable command
            response = await ctrl.execute_command("enable")
            assert response.is_ok
            result = response.unwrap()
            assert "enabled" in result.lower()
        finally:
            ctrl.close()

    @pytest.mark.asyncio
    async def test_ctrl_get_set_props(self):
        """Test getting and setting properties through controller."""
        camera = MockCamera("test_camera")
        ctrl = DeviceController(camera)

        try:
            # Get props
            props = await ctrl.get_props("exposure_ms", "frame_count")
            assert props.res["exposure_ms"].value == 10.0
            assert props.res["frame_count"].value == 0

            # Set props
            result = await ctrl.set_props(exposure_ms=25.0)
            assert result.res["exposure_ms"].value == 25.0
        finally:
            ctrl.close()

    @pytest.mark.asyncio
    async def test_ctrl_interface(self):
        """Test controller interface generation."""
        laser = MockLaser("test_laser")
        ctrl = DeviceController(laser)

        try:
            interface = ctrl.interface
            assert interface.uid == "test_laser"
            assert interface.type == "laser"
            assert "enable" in interface.commands
            assert "power" in interface.properties
        finally:
            ctrl.close()


class TestLocalAdapter:
    """Test LocalAdapter directly."""

    @pytest.mark.asyncio
    async def test_local_adapter_command(self):
        """Test command execution through LocalAdapter."""
        laser = MockLaser("test_laser", max_power=100.0)
        ctrl = DeviceController(laser)
        adapter = LocalAdapter(ctrl)

        try:
            # Set power via props
            await adapter.set_props(power=50.0)

            # Execute command
            response = await adapter.run_command("enable")
            assert response.is_ok
        finally:
            await adapter.close()

    @pytest.mark.asyncio
    async def test_local_adapter_interface(self):
        """Test interface retrieval through LocalAdapter."""
        camera = MockCamera("test_camera")
        ctrl = DeviceController(camera)
        adapter = LocalAdapter(ctrl)

        try:
            interface = await adapter.interface()
            assert interface.uid == "test_camera"
            assert interface.type == "camera"
        finally:
            await adapter.close()

    @pytest.mark.asyncio
    async def test_local_adapter_subscription(self):
        """Test subscription to property changes."""
        # Use StreamingLaser which has stream=True on power property
        laser = StreamingLaser("test_laser")
        ctrl = DeviceController(laser, stream_interval=0.1)
        adapter = LocalAdapter(ctrl)

        received_updates = []

        async def on_props(props):
            received_updates.append(props)

        try:
            await adapter.on_props_changed(on_props)

            # Change a property to trigger update
            await adapter.set_props(power=25.0)

            # Wait for streaming to pick up the change
            await asyncio.sleep(0.3)

            # Should have received at least one update
            assert len(received_updates) >= 1
            # The update should contain the power property
            assert any("power" in update.res for update in received_updates)
        finally:
            await adapter.close()

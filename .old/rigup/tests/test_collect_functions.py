"""Tests for collect_properties and collect_commands functions.

These tests validate that @describe decorators are properly inherited
when properties and methods are overridden in subclasses.
"""

from abc import abstractmethod
from typing import ClassVar

from rigup.device import Device, collect_commands, collect_properties, describe


class SensorBase(Device):
    """Base class with @describe decorated properties and methods."""

    @property
    @abstractmethod
    @describe(label="Sensor Size", units="pixels", desc="Size of the sensor")
    def sensor_size(self) -> int:
        """Get sensor size."""

    @property
    @describe(label="Sensor Temperature", units="°C", desc="Temperature of the sensor")
    def temperature(self) -> float:
        """Get sensor temperature."""
        return 25.0

    @describe(label="Reset Sensor", desc="Reset the sensor to defaults")
    def reset(self) -> None:
        """Reset sensor."""


class ConcreteSensor(SensorBase):
    """Concrete implementation that overrides without re-applying @describe."""

    def __init__(self, uid: str):
        super().__init__(uid)
        self._sensor_size = 1024
        self._temp = 30.0

    @property
    def sensor_size(self) -> int:
        """Overridden without @describe."""
        return self._sensor_size

    @property
    def temperature(self) -> float:
        """Overridden without @describe."""
        return self._temp

    def reset(self) -> None:
        """Overridden without @describe."""
        self._sensor_size = 1024
        self._temp = 25.0


class TestCollectPropertiesBasic:
    """Test basic property collection without inheritance."""

    def test_collects_properties_with_describe_no_inheritance(self):
        """Test that properties with @describe work without inheritance."""

        class SimpleDevice(Device):
            @property
            @describe(label="Simple Prop", units="units", desc="A simple property")
            def simple_prop(self) -> int:
                return 42

        device = SimpleDevice(uid="test")
        props = collect_properties(device)

        assert "simple_prop" in props
        assert props["simple_prop"].label == "Simple Prop"
        assert props["simple_prop"].units == "units"
        assert props["simple_prop"].desc == "A simple property"


class TestCollectPropertiesInheritance:
    """Test that @describe inheritance works for properties."""

    def test_collects_properties_from_device(self):
        """Test that collect_properties finds all properties."""
        sensor = ConcreteSensor(uid="test")
        props = collect_properties(sensor)

        assert "sensor_size" in props
        assert "temperature" in props

    def test_inherits_describe_from_base_abstract_property(self):
        """Test that @describe metadata is inherited from base abstract properties."""
        sensor = ConcreteSensor(uid="test")
        props = collect_properties(sensor)

        sensor_size_info = props["sensor_size"]
        assert sensor_size_info.label == "Sensor Size"
        assert sensor_size_info.units == "pixels"
        assert sensor_size_info.desc == "Size of the sensor"

    def test_inherits_describe_from_base_concrete_property(self):
        """Test that @describe metadata is inherited from base concrete properties."""
        sensor = ConcreteSensor(uid="test")
        props = collect_properties(sensor)

        temp_info = props["temperature"]
        assert temp_info.label == "Sensor Temperature"
        assert temp_info.units == "°C"
        assert temp_info.desc == "Temperature of the sensor"


class TestCollectCommandsBasic:
    """Test basic command collection without inheritance."""

    def test_collects_commands_with_describe_no_inheritance(self):
        """Test that methods with @describe work without inheritance."""

        class SimpleDevice(Device):
            @describe(label="Simple Command", desc="A simple command")
            def simple_cmd(self) -> str:
                return "done"

        device = SimpleDevice(uid="test")
        cmds = collect_commands(device)

        assert "simple_cmd" in cmds
        assert cmds["simple_cmd"].info.label == "Simple Command"
        assert cmds["simple_cmd"].info.desc == "A simple command"


class TestCollectCommandsInheritance:
    """Test that @describe inheritance works for methods."""

    def test_inherits_describe_from_base_method(self):
        """Test that @describe metadata is inherited from base class methods."""
        sensor = ConcreteSensor(uid="test")
        cmds = collect_commands(sensor)

        assert "reset" in cmds
        assert cmds["reset"].info.label == "Reset Sensor"
        assert cmds["reset"].info.desc == "Reset the sensor to defaults"

    def test_calls_child_override_not_base(self):
        """Test that calling the command executes child's override, not base class."""

        class BaseWithCommand(Device):
            def __init__(self, uid: str):
                super().__init__(uid)
                self.call_log = []

            @describe(label="Test Command", desc="A test command")
            def test_cmd(self) -> str:
                self.call_log.append("base")
                return "base"

        class ChildOverride(BaseWithCommand):
            def test_cmd(self) -> str:
                self.call_log.append("child")
                return "child"

        device = ChildOverride(uid="test")
        cmds = collect_commands(device)

        # Should have the command with base class metadata
        assert "test_cmd" in cmds
        assert cmds["test_cmd"].info.label == "Test Command"

        # But calling it should execute the child's override
        result = cmds["test_cmd"]()
        assert result == "child"
        assert device.call_log == ["child"]  # Only child was called, not base


class TestCollectPropertiesEdgeCases:
    """Test edge cases for collect_properties."""

    def test_ignores_private_attributes(self):
        """Test that private attributes are ignored."""
        sensor = ConcreteSensor(uid="test")
        props = collect_properties(sensor)

        # Should not include _sensor_size or _temp
        assert "_sensor_size" not in props
        assert "_temp" not in props

    def test_handles_non_property_attributes(self):
        """Test that non-property attributes are ignored."""
        sensor = ConcreteSensor(uid="test")
        props = collect_properties(sensor)

        # Should not include methods or regular attributes
        assert "reset" not in props
        assert "uid" not in props


class TestCollectCommandsEdgeCases:
    """Test edge cases for collect_commands."""

    def test_ignores_private_methods(self):
        """Test that private methods are ignored."""
        sensor = ConcreteSensor(uid="test")
        cmds = collect_commands(sensor)

        # Should not include __init__ or other private methods
        assert "__init__" not in cmds

    def test_handles_commands_attribute(self):
        """Test that __COMMANDS__ attribute is respected."""

        class DeviceWithCommands(Device):
            __COMMANDS__: ClassVar[set[str]] = {"special_command"}

            def special_command(self):
                return "special"

            def not_a_command(self):
                return "not listed"

        device = DeviceWithCommands(uid="test")
        cmds = collect_commands(device)

        assert "special_command" in cmds
        # not_a_command is not listed and has no @describe, so not included
        assert "not_a_command" not in cmds

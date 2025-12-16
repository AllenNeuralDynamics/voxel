"""Functional tests for Command parameter validation using create_model approach."""

from enum import StrEnum

import pytest
from pydantic import BaseModel

from pyrig.device import Command, CommandParamsError, describe


# Test fixtures - similar to SpimCamera types
class TriggerMode(StrEnum):
    OFF = "off"
    ON = "on"


class TriggerPolarity(StrEnum):
    RISING_EDGE = "rising"
    FALLING_EDGE = "falling"


class ROI(BaseModel):
    x: int
    y: int
    w: int
    h: int


# Test functions
def set_trigger_mode(mode: TriggerMode) -> str:
    """Set trigger mode."""
    return f"Mode set to: {mode}"


def set_exposure(exposure_ms: float, gain: float = 1.0) -> dict:
    """Set exposure with optional gain."""
    return {"exposure": exposure_ms, "gain": gain}


def configure_camera(
    mode: TriggerMode,
    polarity: TriggerPolarity | None = None,
    frame_count: int | None = None,
) -> dict:
    """Configure camera with multiple parameters."""
    return {"mode": mode, "polarity": polarity, "frame_count": frame_count}


def set_roi(roi: ROI) -> str:
    """Set region of interest."""
    return f"ROI set to: {roi}"


@describe(label="Add Numbers", desc="Adds two integers")
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


# Tests
class TestEnumValidation:
    """Test enum parameter validation and coercion."""

    def test_enum_from_string_value(self):
        """Test that string values are coerced to enums."""
        cmd = Command(set_trigger_mode)
        result = cmd(mode="on")
        assert result == "Mode set to: on"

    def test_enum_from_enum_instance(self):
        """Test that enum instances work directly."""
        cmd = Command(set_trigger_mode)
        result = cmd(mode=TriggerMode.OFF)
        assert result == "Mode set to: off"

    def test_enum_invalid_value(self):
        """Test that invalid enum values raise errors."""
        cmd = Command(set_trigger_mode)
        with pytest.raises(CommandParamsError) as exc_info:
            cmd(mode="invalid")

        assert len(exc_info.value.errors) == 1
        assert "mode:" in exc_info.value.errors[0]

    def test_enum_case_sensitive(self):
        """Test that enum values are case-sensitive."""
        cmd = Command(set_trigger_mode)
        with pytest.raises(CommandParamsError):
            cmd(mode="ON")  # Should fail - must be lowercase "on"


class TestOptionalParameters:
    """Test optional parameters and defaults."""

    def test_required_only(self):
        """Test with only required parameters."""
        cmd = Command(set_exposure)
        result = cmd(exposure_ms=100.0)
        assert result == {"exposure": 100.0, "gain": 1.0}

    def test_with_optional(self):
        """Test with optional parameters provided."""
        cmd = Command(set_exposure)
        result = cmd(exposure_ms=100.0, gain=2.5)
        assert result == {"exposure": 100.0, "gain": 2.5}

    def test_missing_required(self):
        """Test that missing required parameters raise errors."""
        cmd = Command(set_exposure)
        with pytest.raises(CommandParamsError) as exc_info:
            cmd(gain=2.5)  # Missing required exposure_ms

        assert len(exc_info.value.errors) == 1
        assert "exposure_ms" in exc_info.value.errors[0]


class TestUnionTypes:
    """Test Union types including None (Optional)."""

    def test_required_only(self):
        """Test with only required parameter."""
        cmd = Command(configure_camera)
        result = cmd(mode="on")
        assert result["mode"] == "on"
        assert result["polarity"] is None
        assert result["frame_count"] is None

    def test_with_optional_enum(self):
        """Test with optional enum parameter."""
        cmd = Command(configure_camera)
        result = cmd(mode="on", polarity="rising")
        assert result["mode"] == "on"
        assert result["polarity"] == "rising"

    def test_with_all_parameters(self):
        """Test with all parameters."""
        cmd = Command(configure_camera)
        result = cmd(mode="off", polarity="falling", frame_count=100)
        assert result["mode"] == "off"
        assert result["polarity"] == "falling"
        assert result["frame_count"] == 100


class TestNestedPydanticModels:
    """Test nested Pydantic model parameters."""

    def test_model_from_dict(self):
        """Test that dict is coerced to Pydantic model."""
        cmd = Command(set_roi)
        result = cmd(roi={"x": 10, "y": 20, "w": 100, "h": 200})
        # After validation, model_dump() converts it back to dict
        assert "'x': 10" in result
        assert "'y': 20" in result

    def test_model_from_instance(self):
        """Test that model instances work directly."""
        cmd = Command(set_roi)
        roi = ROI(x=10, y=20, w=100, h=200)
        result = cmd(roi=roi)
        # After validation, model_dump() converts it to dict
        assert "'x': 10" in result

    def test_model_invalid_dict(self):
        """Test that invalid dicts raise validation errors."""
        cmd = Command(set_roi)
        with pytest.raises(CommandParamsError) as exc_info:
            cmd(roi={"x": 10, "y": 20})  # Missing w and h

        assert len(exc_info.value.errors) >= 1


class TestBasicTypes:
    """Test basic type validation and coercion."""

    def test_int_validation(self):
        """Test integer type validation."""
        cmd = Command(add_numbers)
        result = cmd(a=5, b=10)
        assert result == 15

    def test_int_coercion_from_string(self):
        """Test that Pydantic coerces string to int when possible."""
        cmd = Command(add_numbers)
        result = cmd(a="5", b="10")
        assert result == 15

    def test_int_invalid_string(self):
        """Test that invalid strings raise errors."""
        cmd = Command(add_numbers)
        with pytest.raises(CommandParamsError):
            cmd(a="not_a_number", b=10)


class TestPositionalArguments:
    """Test positional argument handling."""

    def test_positional_args(self):
        """Test that positional args are converted to kwargs."""
        cmd = Command(add_numbers)
        result = cmd(5, 10)
        assert result == 15

    def test_mixed_args_kwargs(self):
        """Test mixing positional and keyword arguments."""
        cmd = Command(add_numbers)
        result = cmd(5, b=10)
        assert result == 15


class TestCommandMetadata:
    """Test that command metadata is preserved."""

    def test_command_info_preserved(self):
        """Test that CommandInfo is still generated correctly."""
        cmd = Command(add_numbers)
        assert cmd.info.name == "add_numbers"
        assert cmd.info.label == "Add Numbers"
        assert cmd.info.desc == "Adds two integers"

    def test_to_dict_serialization(self):
        """Test JSON serialization still works."""
        cmd = Command(add_numbers)
        cmd_dict = cmd.to_dict()
        assert cmd_dict["name"] == "add_numbers"
        assert "params" in cmd_dict


class TestErrorMessages:
    """Test that error messages are clear and helpful."""

    def test_validation_error_format(self):
        """Test that Pydantic validation errors are formatted correctly."""
        cmd = Command(add_numbers)
        with pytest.raises(CommandParamsError) as exc_info:
            cmd(a="invalid", b=10)

        error = exc_info.value
        assert error.cmd == cmd
        assert len(error.errors) == 1
        assert "a:" in error.errors[0]

    def test_multiple_validation_errors(self):
        """Test that multiple errors are reported together."""
        cmd = Command(add_numbers)
        with pytest.raises(CommandParamsError) as exc_info:
            cmd(a="invalid1", b="invalid2")

        # Should report errors for both parameters
        errors_str = str(exc_info.value)
        assert "a:" in errors_str

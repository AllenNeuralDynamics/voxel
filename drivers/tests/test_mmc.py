from collections import deque
from unittest.mock import patch

import pytest
from rigup.device.props import PropertyModel
from rigup.device.schema import Result, collect_commands, collect_properties
from vxl_drivers.axes.mmc import MMCLinearAxis
from vxl_drivers.axes.mmc._cmds import (
    Cmd,
    parse_controller_error,
    parse_deadband,
    parse_limit_status,
    parse_position,
    parse_status,
)
from vxl_drivers.axes.mmc._hub import MMCAxisAlreadyReservedError, MMCHub


class FakeSerial:
    def __init__(self, responses: list[bytes] | None = None) -> None:
        self.responses = deque(responses or [])
        self.writes: list[bytes] = []
        self.reset_count = 0
        self.flush_count = 0
        self.is_open = True
        self.port = "test"
        self.timeout: float | None = 0.5

    def reset_input_buffer(self) -> None:
        self.reset_count += 1

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    def flush(self) -> None:
        self.flush_count += 1

    def read_until(self, terminator: bytes) -> bytes:
        assert terminator == b"\r"
        return self.responses.popleft() if self.responses else b""

    def close(self) -> None:
        self.is_open = False


def make_hub(port: FakeSerial) -> MMCHub:
    with patch("vxl_drivers.serial.serial.Serial", return_value=port):
        return MMCHub("test", uid="hub")


def test_hub_frames_commands_and_cleans_multiline_responses() -> None:
    port = FakeSerial([b"#11 - Motor Disabled [MVA]\n#12 - No Encoder Detected [POS]\n\r"])
    hub = make_hub(port)

    hub.command(2, Cmd.MOVE_ABSOLUTE, 1.25)
    errors = hub.query_lines(2, Cmd.READ_ERRORS)

    assert port.writes == [b"2MVA1.25\r", b"2ERR?\r"]
    assert errors == ("11 - Motor Disabled [MVA]", "12 - No Encoder Detected [POS]")


def test_hub_rejects_duplicate_axis_reservations() -> None:
    hub = make_hub(FakeSerial())
    hub.reserve_axis(1)

    with pytest.raises(MMCAxisAlreadyReservedError):
        hub.reserve_axis(1)

    hub.release_axis(1)
    hub.reserve_axis(1)


def test_protocol_parsers_match_manual_response_shapes() -> None:
    position = parse_position("[1.25, 1.249]")
    status = parse_status("171")
    limits = parse_limit_status("1,0")
    deadband = parse_deadband("10,1.5")
    error = parse_controller_error("12 - No Encoder Detected [POS]")

    assert position.theoretical == 1.25
    assert position.encoder == 1.249
    assert status.has_error
    assert status.at_constant_velocity
    assert status.stopped
    assert status.program_running is False
    assert status.positive_limit_active
    assert status.negative_limit_active
    assert limits.positive_active
    assert not limits.negative_active
    assert deadband.counts == 10
    assert deadband.timeout_s == 1.5
    assert error.code == 12
    assert error.message == "No Encoder Detected"
    assert error.command == "POS"


def test_axis_converts_units_and_exposes_serializable_status() -> None:
    port = FakeSerial(
        [
            b"#1.4.53\n\r",
            b"#0\n\r",
            b"#10\n\r",
            b"#1.25,1.249\n\r",
            b"#136\n\r",
        ]
    )
    hub = make_hub(port)
    axis = MMCLinearAxis(hub=hub, axis_id=2, uid="selector", units="um")

    assert axis.firmware_version == "1.4.53"
    assert axis.position == 1250
    status_model = PropertyModel.from_value(axis.status)
    axis.move_abs(2500)

    assert status_model.model_dump(mode="json")["value"] == {
        "raw": 136,
        "has_error": True,
        "accelerating": False,
        "at_constant_velocity": False,
        "decelerating": False,
        "stopped": True,
        "program_running": False,
        "positive_limit_active": False,
        "negative_limit_active": False,
    }
    assert port.writes == [
        b"2VER?\r",
        b"2TLN?\r",
        b"2TLP?\r",
        b"2POS?\r",
        b"2STA?\r",
        b"2MVA2.5\r",
    ]


def test_axis_rejects_nonzero_logical_position() -> None:
    hub = make_hub(FakeSerial([b"#1.4.53\n\r", b"#0\n\r", b"#10\n\r"]))
    axis = MMCLinearAxis(hub=hub, axis_id=1, uid="axis")

    with pytest.raises(NotImplementedError, match="zeroing"):
        axis.set_logical_position(1)


def test_home_uses_blocking_home_query_instead_of_status_polling() -> None:
    port = FakeSerial(
        [
            b"#1.4.53\n\r",
            b"#0\n\r",
            b"#10\n\r",
            b"#1\n\r",
            b"#8\n\r",
        ]
    )
    hub = make_hub(port)
    axis = MMCLinearAxis(hub=hub, axis_id=1, uid="axis")

    axis.go_home(wait=True, timeout_s=12)

    assert port.writes[-3:] == [b"1HOM\r", b"1HOM?\r", b"1STA?\r"]
    assert port.timeout == 0.5


def test_axis_rigup_interface_is_curated_and_structured_results_serialize() -> None:
    hub = make_hub(FakeSerial([b"#1.4.53\n\r", b"#0\n\r", b"#10\n\r"]))
    axis = MMCLinearAxis(hub=hub, axis_id=1, uid="axis")

    properties = collect_properties(axis)
    commands = collect_commands(axis)
    error = parse_controller_error("12 - No Encoder Detected [POS]")

    assert {
        "feedback_mode",
        "motor_enabled",
        "status",
        "position_reading",
        "deadband",
        "encoder_type",
    } <= properties.keys()
    assert properties["position"].stream
    assert properties["is_moving"].stream
    assert not properties["speed"].stream
    assert not properties["acceleration"].stream
    assert {
        "move_abs",
        "halt",
        "stop",
        "configure_deadband",
        "read_and_clear_errors",
        "save_settings",
    } <= commands.keys()
    assert Result.ok([error]).model_dump(mode="json") == {
        "ok": True,
        "value": [
            {
                "code": 12,
                "message": "No Encoder Detected",
                "command": "POS",
                "raw": "12 - No Encoder Detected [POS]",
            }
        ],
    }

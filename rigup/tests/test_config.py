"""Tests for rigup.config — NodeConfig autofill, validation, RigConfig shape."""

import pytest
from pydantic import ValidationError
from rigup.build import BuildConfig, dependencies
from rigup.config import NodeConfig, RigConfig
from rigup.device import CommandRequest
from rigup.protocol import BuildDevicesRequest

from rigup import Part

_MAIN = {
    "parts": {"glass": {"kind": "filter"}},
    "devices": {"camera": {"target": "some.Camera", "details": {"vendor": "ACME"}}},
}
_NESTED = {
    "parts": {"glass": {"target": "tests._mock.MockPart", "value": 1.5, "details": {"serial": "42"}}},
    "devices": {"camera": {"target": "some.Camera"}},
    "nodes": {
        "detection": {
            "address": "tcp://10.0.0.2:5555",
            "devices": {"wheel": {"target": "some.Wheel", "init": {"slots": {"0": "glass"}}}},
        },
    },
}


def test_parts_survive_config_and_build_request_roundtrips():
    restored = RigConfig.model_validate_json(RigConfig.model_validate(_NESTED).model_dump_json())
    request = BuildDevicesRequest(devices=restored.nodes["detection"].devices, parts=restored.parts)
    received = BuildDevicesRequest.model_validate_json(request.model_dump_json())
    assert received.parts == restored.parts
    assert type(received.parts["glass"]).__name__ == "MockPart"
    assert received.parts["glass"].details == {"serial": "42"}


class TestRigNodes:
    def test_top_level_devices_are_the_app_s_own_process(self):
        cfg = RigConfig.model_validate(_MAIN)
        assert cfg.nodes == {}
        assert set(cfg.devices) == set(cfg.all_devices) == {"camera"}
        assert set(cfg.parts) == {"glass"}

    def test_a_file_keeps_its_nodes(self):
        cfg = RigConfig.model_validate(_NESTED)
        assert set(cfg.nodes) == {"detection"}
        assert cfg.nodes["detection"].kind == "remote"
        assert set(cfg.devices) == {"camera"}
        assert set(cfg.all_devices) == {"camera", "wheel"}
        assert RigConfig.model_validate(cfg.model_dump(mode="json")) == cfg

    def test_a_node_is_never_local(self):
        with pytest.raises(ValidationError, match="Input should be 'subprocess' or 'remote'"):
            NodeConfig.model_validate({"kind": "local"})

    def test_an_empty_nodes_value_is_a_validation_error(self):
        with pytest.raises(ValidationError, match="valid dictionary"):
            RigConfig.model_validate({"nodes": None})

    def test_component_location_says_where_a_component_is_written(self):
        cfg = RigConfig.model_validate(_NESTED)
        assert cfg.component_location("glass") == ("parts", "glass")
        assert cfg.component_location("camera") == ("devices", "camera")
        assert cfg.component_location("wheel") == ("nodes", "detection", "devices", "wheel")


class TestRigParts:
    def test_a_part_is_made_when_the_file_is_read(self):
        glass = RigConfig.model_validate(_NESTED).parts["glass"]
        assert (type(glass).__name__, glass.uid, glass.kind) == ("MockPart", "glass", "mock_part")
        plain = RigConfig.model_validate(_MAIN).parts["glass"]
        assert (type(plain), plain.uid, plain.kind) == (Part, "glass", "filter")

    def test_a_part_is_written_back_as_its_fields(self):
        assert RigConfig.model_validate(_NESTED).model_dump(mode="json")["parts"] == _NESTED["parts"]
        assert RigConfig.model_validate(_MAIN).model_dump(mode="json")["parts"] == _MAIN["parts"]

    def test_each_bad_part_is_a_problem_at_its_field(self):
        with pytest.raises(ValidationError) as caught:
            RigConfig.model_validate(
                {
                    "parts": {
                        "a": {"target": "tests._mock.MockPart", "value": "high"},
                        "b": {"kind": "filter", "band": [500, 550]},
                        "c": {"target": "tests._mock.NoSuchPart", "kind": "x"},
                    }
                }
            )

        assert [error["loc"] for error in caught.value.errors()] == [
            ("parts", "a", "value"),
            ("parts", "b", "band"),
            ("parts", "c"),
        ]


class TestRigProblems:
    def test_each_problem_has_its_code_and_its_place_in_the_file(self):
        with pytest.raises(ValidationError) as caught:
            RigConfig.model_validate(
                {
                    "parts": {"camera": {"kind": "spot"}, "glass": {"kind": "filter"}},
                    "devices": {"camera": {"target": "some.Camera"}},
                    "nodes": {
                        "detection": {
                            "kind": "subprocess",
                            "devices": {"wheel": {"target": "some.Wheel", "init": {"hub": "hub", "slot": "glass"}}},
                        },
                        "motion": {"kind": "subprocess", "devices": {"hub": {"target": "some.Hub"}}},
                    },
                }
            )

        assert [(error["type"], error["loc"]) for error in caught.value.errors()] == [
            ("duplicate_uid", ("devices", "camera")),
            ("cross_node_reference", ("nodes", "detection", "devices", "wheel")),
        ]

    def test_a_node_problem_is_at_its_node(self):
        with pytest.raises(ValidationError) as caught:
            RigConfig.model_validate(
                {"nodes": {"near": {"address": None, "kind": "remote"}, "far": {"kind": "remote"}}}
            )

        assert [(error["type"], error["loc"]) for error in caught.value.errors()] == [
            ("remote_node_address", ("nodes", "near", "address")),
            ("remote_node_address", ("nodes", "far", "address")),
        ]


class TestNodeConfigKindAutofill:
    def test_no_address_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"devices": {}})
        assert cfg.kind == "subprocess"

    def test_localhost_tcp_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"address": "tcp://localhost:5555"})
        assert cfg.kind == "subprocess"

    def test_loopback_tcp_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"address": "tcp://127.0.0.1:5555"})
        assert cfg.kind == "subprocess"

    def test_ipv6_loopback_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"address": "tcp://[::1]:5555"})
        assert cfg.kind == "subprocess"

    def test_bind_any_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"address": "tcp://*:5555"})
        assert cfg.kind == "subprocess"

    def test_ipc_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"address": "ipc:///tmp/test"})
        assert cfg.kind == "subprocess"

    def test_remote_host_infers_remote(self):
        cfg = NodeConfig.model_validate({"address": "tcp://10.0.0.2:5555"})
        assert cfg.kind == "remote"

    def test_explicit_kind_overrides_autofill(self):
        cfg = NodeConfig.model_validate({"kind": "remote", "address": "tcp://localhost:5555"})
        assert cfg.kind == "remote"


class TestNodeConfigValidation:
    def test_remote_without_address_raises(self):
        with pytest.raises(ValidationError):
            NodeConfig.model_validate({"kind": "remote"})

    def test_subprocess_without_address_is_valid(self):
        cfg = NodeConfig.model_validate({"kind": "subprocess"})
        assert cfg.address is None

    def test_subprocess_with_address_is_valid(self):
        cfg = NodeConfig.model_validate({"kind": "subprocess", "address": "tcp://localhost:5555"})
        assert cfg.address == "tcp://localhost:5555"

    def test_unknown_field_is_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            NodeConfig.model_validate({"kind": "subprocess", "adress": "tcp://localhost:5555"})


class TestRigConfig:
    def test_minimal_config(self):
        cfg = RigConfig.model_validate({})
        assert cfg.nodes == {}
        assert cfg.devices == cfg.parts == {}

    def test_devices_and_nodes(self):
        cfg = RigConfig.model_validate(
            {
                "devices": {"stage": {"target": "some.Module", "init": {}}},
                "nodes": {"cam_host": {"address": "tcp://10.0.0.2:5555"}},
            }
        )
        assert "stage" in cfg.devices
        assert cfg.nodes["cam_host"].kind == "remote"
        assert cfg.nodes["cam_host"].address == "tcp://10.0.0.2:5555"

    def test_unknown_field_is_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            RigConfig.model_validate({"name": "test"})

    def test_unknown_device_build_field_is_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            BuildConfig.model_validate({"target": "some.Module", "initial": {}})

    def test_unknown_command_request_field_is_rejected(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CommandRequest.model_validate({"attr": "enable", "arguments": []})

    def test_device_uids_must_be_unique_across_nodes(self):
        with pytest.raises(ValidationError, match="Component UID 'camera' is duplicated"):
            RigConfig.model_validate(
                {
                    "devices": {"camera": {"target": "some.Camera"}},
                    "nodes": {
                        "remote": {
                            "kind": "subprocess",
                            "devices": {"camera": {"target": "some.OtherCamera"}},
                        },
                    },
                }
            )

    def test_same_node_device_reference_is_valid(self):
        cfg = RigConfig.model_validate(
            {
                "nodes": {
                    "motion": {
                        "kind": "subprocess",
                        "devices": {
                            "hub": {"target": "some.Hub"},
                            "axis": {"target": "some.Axis", "init": {"hub": "hub"}},
                        },
                    }
                }
            }
        )

        assert cfg.nodes["motion"].devices["axis"].init["hub"] == "hub"

    def test_dependencies_are_the_devices_that_init_names(self):
        cfg = RigConfig.model_validate(
            {
                "devices": {
                    "hub": {"target": "some.Hub", "init": {"port": "COM4"}},
                    "axis": {"target": "some.Axis", "init": {"hub": "hub", "label": "axis"}},
                    "pair": {"target": "some.Pair", "init": {"members": {"first": ["axis"], "second": "hub"}}},
                }
            }
        )

        assert dependencies(cfg.devices, "hub") == set()
        assert dependencies(cfg.devices, "axis") == {"hub"}
        assert dependencies(cfg.devices, "pair") == {"axis", "hub"}

    def test_cross_node_device_reference_is_rejected(self):
        with pytest.raises(ValidationError, match="constructor-injected dependencies must be in the same process"):
            RigConfig.model_validate(
                {
                    "nodes": {
                        "motion": {
                            "kind": "subprocess",
                            "devices": {"hub": {"target": "some.Hub"}},
                        },
                        "camera": {
                            "kind": "subprocess",
                            "devices": {
                                "camera": {
                                    "target": "some.Camera",
                                    "init": {"trigger_source": {"devices": ["hub"]}},
                                }
                            },
                        },
                    }
                }
            )

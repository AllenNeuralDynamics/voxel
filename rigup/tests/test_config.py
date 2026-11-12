"""Tests for rigup.config — NodeConfig autofill, validation, RigConfig shape."""

import pytest
from pydantic import ValidationError
from rigup.build import BuildConfig
from rigup.config import ComponentConfig, NodeConfig, RigConfig
from rigup.device import CommandRequest
from rigup.protocol import BuildDevicesRequest


def test_details_survive_config_and_build_request_roundtrips():
    cfg = RigConfig(
        components={"local": ComponentConfig(target="some.Device", details={"vendor": "ACME"})},
        nodes={
            "remote": NodeConfig(
                kind="remote",
                address="tcp://10.0.0.2:5555",
                components={"camera": ComponentConfig(target="some.Camera", details={"serial": "42"})},
            )
        },
    )
    restored = RigConfig.model_validate_json(cfg.model_dump_json())
    assert restored.components["local"].details == {"vendor": "ACME"}
    request = BuildDevicesRequest(devices=restored.nodes["remote"].components)
    received = BuildDevicesRequest.model_validate_json(request.model_dump_json())
    assert received.devices["camera"].details == {"serial": "42"}


class TestNodeConfigKindAutofill:
    def test_no_address_infers_subprocess(self):
        cfg = NodeConfig.model_validate({"components": {}})
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
        assert cfg.components == {}
        assert cfg.nodes == {}

    def test_devices_and_nodes(self):
        cfg = RigConfig.model_validate(
            {
                "components": {"stage": {"target": "some.Module", "init": {}}},
                "nodes": {"cam_host": {"address": "tcp://10.0.0.2:5555", "components": {}}},
            }
        )
        assert "stage" in cfg.components
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
                    "components": {"camera": {"target": "some.Camera"}},
                    "nodes": {
                        "remote": {
                            "kind": "subprocess",
                            "components": {"camera": {"target": "some.OtherCamera"}},
                        }
                    },
                }
            )

    def test_same_node_device_reference_is_valid(self):
        cfg = RigConfig.model_validate(
            {
                "nodes": {
                    "motion": {
                        "kind": "subprocess",
                        "components": {
                            "hub": {"target": "some.Hub"},
                            "axis": {"target": "some.Axis", "init": {"hub": "hub"}},
                        },
                    }
                }
            }
        )

        assert cfg.nodes["motion"].components["axis"].init["hub"] == "hub"

    def test_references_are_the_devices_that_init_names(self):
        cfg = RigConfig.model_validate(
            {
                "components": {
                    "hub": {"target": "some.Hub", "init": {"port": "COM4"}},
                    "axis": {"target": "some.Axis", "init": {"hub": "hub", "label": "axis"}},
                    "pair": {"target": "some.Pair", "init": {"members": {"first": ["axis"], "second": "hub"}}},
                }
            }
        )

        assert cfg.references("hub") == set()
        assert cfg.references("axis") == {"hub"}
        assert cfg.references("pair") == {"axis", "hub"}

    def test_cross_node_device_reference_is_rejected(self):
        with pytest.raises(ValidationError, match="constructor-injected dependencies must be on the same node"):
            RigConfig.model_validate(
                {
                    "nodes": {
                        "motion": {
                            "kind": "subprocess",
                            "components": {"hub": {"target": "some.Hub"}},
                        },
                        "camera": {
                            "kind": "subprocess",
                            "components": {
                                "camera": {
                                    "target": "some.Camera",
                                    "init": {"trigger_source": {"devices": ["hub"]}},
                                }
                            },
                        },
                    }
                }
            )

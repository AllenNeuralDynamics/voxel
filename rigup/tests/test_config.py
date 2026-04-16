"""Tests for rigup.config — NodeConfig autofill, validation, RigConfig shape."""

import pytest
from pydantic import ValidationError
from rigup.config import NodeConfig, RigConfig


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


class TestRigConfig:
    def test_minimal_config(self):
        cfg = RigConfig.model_validate({"name": "test"})
        assert cfg.name == "test"
        assert cfg.devices == {}
        assert cfg.nodes == {}

    def test_devices_and_nodes(self):
        cfg = RigConfig.model_validate(
            {
                "name": "test",
                "devices": {"stage": {"target": "some.Module", "init": {}}},
                "nodes": {"cam_host": {"address": "tcp://10.0.0.2:5555", "devices": {}}},
            }
        )
        assert "stage" in cfg.devices
        assert cfg.nodes["cam_host"].kind == "remote"
        assert cfg.nodes["cam_host"].address == "tcp://10.0.0.2:5555"

    def test_default_name(self):
        cfg = RigConfig()
        assert cfg.name == "rig"

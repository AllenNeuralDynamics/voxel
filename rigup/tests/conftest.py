"""Shared fixtures for rigup tests."""

import socket

import pytest
from rigup.config import DeviceConfig, RigConfig
from rigup.transport import TCPAddress

MOCK_TARGET = "tests._mock.MockDevice"


@pytest.fixture
def mock_device_config() -> DeviceConfig:
    return DeviceConfig(target=MOCK_TARGET, init={"initial_value": 1.0})


@pytest.fixture
def local_rig_config(mock_device_config: DeviceConfig) -> RigConfig:
    return RigConfig(
        devices={
            "device_a": mock_device_config,
            "device_b": DeviceConfig(target=MOCK_TARGET, init={"initial_value": 2.0}),
        },
    )


@pytest.fixture
def free_tcp_address() -> TCPAddress:
    """Find two free TCP ports and return a TCPAddress."""
    socks = []
    ports = []
    for _ in range(2):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        ports.append(s.getsockname()[1])
        socks.append(s)
    for s in socks:
        s.close()
    return TCPAddress(host="127.0.0.1", rpc_port=ports[0], pub_port=ports[1])

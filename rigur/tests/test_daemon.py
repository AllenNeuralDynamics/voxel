"""Tests for NodeDaemon — full remote device path via transport."""

import asyncio

import pytest

from rigur.node import NodeDaemon
from rigur.protocol import (
    Action,
    BuildDevicesRequest,
    BuildDevicesResponse,
    ClaimRequest,
    ClaimResponse,
    CloseDeviceRequest,
    Empty,
    GetInterfaceRequest,
    GetPropsRequest,
    ListDevicesResponse,
    Notify,
    PingPayload,
    ReleaseRequest,
    ReleaseResponse,
    RunCommandsRequest,
    SetPropsRequest,
    ShutdownPayload,
    call,
    send_notify,
)
from rigur.transport import TCPAddress, ZMQTransportClient, ZMQTransportServer

MOCK_TARGET = "tests._mock.MockDevice"


@pytest.fixture
async def daemon_pair(free_tcp_address: TCPAddress):
    """Yields a connected (client, daemon) pair with transport wired up."""
    server_transport = ZMQTransportServer()
    daemon = NodeDaemon(node_id="test-daemon", transport=server_transport)
    await daemon.start(free_tcp_address)

    client = ZMQTransportClient()
    await client.connect(free_tcp_address)

    # Verify connectivity
    pong = await call(client, Action.PING, PingPayload(timestamp=1.0), PingPayload, timeout_s=5.0)
    assert pong.timestamp == 1.0

    yield client, daemon

    await client.close()
    await daemon.stop()


class TestDaemonAuthority:
    async def test_claim_and_release(self, daemon_pair):
        client, _daemon = daemon_pair

        resp = await call(client, Action.CLAIM, ClaimRequest(orchestrator_id="rig-1"), ClaimResponse, timeout_s=5.0)
        assert resp.accepted

        resp = await call(client, Action.RELEASE, ReleaseRequest(orchestrator_id="rig-1"), ReleaseResponse, timeout_s=5.0)
        assert resp.released

    async def test_second_claim_rejected(self, daemon_pair):
        client, _daemon = daemon_pair

        await call(client, Action.CLAIM, ClaimRequest(orchestrator_id="rig-1"), ClaimResponse, timeout_s=5.0)

        resp = await call(client, Action.CLAIM, ClaimRequest(orchestrator_id="rig-2"), ClaimResponse, timeout_s=5.0)
        assert not resp.accepted
        assert resp.current_owner == "rig-1"

    async def test_same_orchestrator_can_reclaim(self, daemon_pair):
        client, _daemon = daemon_pair

        await call(client, Action.CLAIM, ClaimRequest(orchestrator_id="rig-1"), ClaimResponse, timeout_s=5.0)

        resp = await call(client, Action.CLAIM, ClaimRequest(orchestrator_id="rig-1"), ClaimResponse, timeout_s=5.0)
        assert resp.accepted


class TestDaemonDeviceLifecycle:
    async def test_build_and_list_devices(self, daemon_pair):
        client, _daemon = daemon_pair

        build_resp = await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={
                "dev_a": {"target": MOCK_TARGET, "init": {"initial_value": 1.0}},
                "dev_b": {"target": MOCK_TARGET, "init": {"initial_value": 2.0}},
            }),
            BuildDevicesResponse,
            timeout_s=10.0,
        )
        assert len(build_resp.built) == 2
        assert not build_resp.errors
        assert "dev_a" in build_resp.built

        list_resp = await call(client, Action.LIST_DEVICES, Empty(), ListDevicesResponse, timeout_s=5.0)
        assert len(list_resp.devices) == 2

    async def test_close_device(self, daemon_pair):
        client, _daemon = daemon_pair

        await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={"dev": {"target": MOCK_TARGET, "init": {}}}),
            BuildDevicesResponse,
            timeout_s=10.0,
        )

        await call(client, Action.CLOSE_DEVICE, CloseDeviceRequest(uid="dev"), Empty, timeout_s=5.0)

        list_resp = await call(client, Action.LIST_DEVICES, Empty(), ListDevicesResponse, timeout_s=5.0)
        assert len(list_resp.devices) == 0

    async def test_build_clears_previous(self, daemon_pair):
        client, _daemon = daemon_pair

        await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={"old": {"target": MOCK_TARGET, "init": {}}}),
            BuildDevicesResponse,
            timeout_s=10.0,
        )

        await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={"new": {"target": MOCK_TARGET, "init": {}}}),
            BuildDevicesResponse,
            timeout_s=10.0,
        )

        list_resp = await call(client, Action.LIST_DEVICES, Empty(), ListDevicesResponse, timeout_s=5.0)
        assert "new" in list_resp.devices
        assert "old" not in list_resp.devices

    async def test_build_with_bad_target(self, daemon_pair):
        client, _daemon = daemon_pair

        resp = await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={"bad": {"target": "nonexistent.Mod", "init": {}}}),
            BuildDevicesResponse,
            timeout_s=10.0,
        )
        assert not resp.built
        assert "bad" in resp.errors


class TestDaemonDeviceRPC:
    @pytest.fixture
    async def built_daemon(self, daemon_pair):
        client, daemon = daemon_pair
        await call(
            client,
            Action.BUILD_DEVICES,
            BuildDevicesRequest(devices={"dev": {"target": MOCK_TARGET, "init": {"initial_value": 5.0}}}),
            BuildDevicesResponse,
            timeout_s=10.0,
        )
        return client, daemon

    async def test_run_commands(self, built_daemon):
        client, _ = built_daemon
        from rigur.device import CommandRequest, Results

        resp = await call(
            client,
            Action.RUN_COMMANDS,
            RunCommandsRequest(uid="dev", commands=[CommandRequest(attr="set_value", kwargs={"v": 99.0})]),
            Results,
            timeout_s=5.0,
        )
        assert resp.is_ok

    async def test_get_props(self, built_daemon):
        client, _ = built_daemon
        from rigur.device import PropResults

        resp = await call(
            client,
            Action.GET_PROPS,
            GetPropsRequest(uid="dev", props=["value"]),
            PropResults,
            timeout_s=5.0,
        )
        assert resp["value"].unwrap().value == 5.0

    async def test_set_props(self, built_daemon):
        client, _ = built_daemon
        from rigur.device import PropResults

        resp = await call(
            client,
            Action.SET_PROPS,
            SetPropsRequest(uid="dev", props={"value": 42.0}),
            PropResults,
            timeout_s=5.0,
        )
        assert resp["value"].unwrap().value == 42.0

    async def test_get_interface(self, built_daemon):
        client, _ = built_daemon
        from rigur.device import DeviceInterface

        iface = await call(
            client,
            Action.GET_INTERFACE,
            GetInterfaceRequest(uid="dev"),
            DeviceInterface,
            timeout_s=5.0,
        )
        assert iface.type == "mock"
        assert "set_value" in iface.commands


class TestDaemonShutdown:
    async def test_shutdown_notify(self, free_tcp_address: TCPAddress):
        server_transport = ZMQTransportServer()
        daemon = NodeDaemon(node_id="shutdown-test", transport=server_transport)
        await daemon.start(free_tcp_address)

        client = ZMQTransportClient()
        await client.connect(free_tcp_address)

        # Verify alive
        await call(client, Action.PING, PingPayload(), PingPayload, timeout_s=5.0)

        # Send shutdown — daemon should unblock serve_until_shutdown
        shutdown_task = asyncio.create_task(daemon.serve_until_shutdown())
        await asyncio.sleep(0.05)
        assert not shutdown_task.done()

        await send_notify(client, Notify.SHUTDOWN, ShutdownPayload(reason="test"))
        await asyncio.wait_for(shutdown_task, timeout=5.0)

        await client.close()
        await daemon.stop()

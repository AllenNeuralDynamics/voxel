from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from rigup.device.handle import Adapter, DeviceProperties

from rigup import BuildConfig, BuildError, DeviceHandle, DeviceInterface, PropertyModel, PropResults, Result
from vxl.hal.core import HAL
from vxl.hal.errors import HALStartupError
from vxl.hal.topology import (
    DetectionAssembly,
    HardwareTopology,
    IlluminationAssembly,
    OpticalRouteDefinition,
    OpticalRouting,
    StageAxes,
)


class _FakeRig:
    def __init__(
        self,
        *,
        devices: dict[str, DeviceHandle] | None = None,
        build_errors: dict[str, BuildError] | None = None,
    ) -> None:
        self.devices = devices or {}
        self.build_errors = build_errors or {}
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True
        self.devices.clear()
        self.build_errors.clear()


def _handle(uid: str, device_type: str = "camera", *, properties=None, property_error=None, interface_error=None):
    adapter = Mock(spec=Adapter)
    adapter.uid = uid
    adapter.cached_interface = AsyncMock(
        return_value=DeviceInterface(uid=uid, type=device_type, commands={}, properties={}), side_effect=interface_error
    )
    adapter.props = Mock(spec=DeviceProperties)
    adapter.props.get = AsyncMock(return_value=properties, side_effect=property_error)
    return DeviceHandle(adapter)


def _hal_config() -> HardwareTopology:
    uids = {"camera", "laser", "x", "y", "z", "filter"}
    devices = {uid: BuildConfig(target="builtins.object") for uid in uids}
    return HardwareTopology(
        devices=devices,
        stage=StageAxes(x="x", y="y", z="z"),
        detection={
            "camera": DetectionAssembly(
                filter_wheels=["filter"],
                magnification=1,
                rotation_deg=0,
            )
        },
        illumination={"laser": IlluminationAssembly()},
    )


def _routed_hal_config() -> HardwareTopology:
    config = _hal_config()
    return config.model_copy(
        update={
            "devices": {
                **config.devices,
                "selector": BuildConfig(
                    target="builtins.object",
                    init={"slots": {0: "left", 1: "right"}},
                ),
            },
            "illumination": {"laser": IlluminationAssembly(routing={"excitation_side"})},
            "optical_routing": OpticalRouting(
                {
                    "excitation_side": {
                        "left": OpticalRouteDefinition({"selector": "left"}),
                        "right": OpticalRouteDefinition({"selector": "right"}),
                    }
                }
            ),
        }
    )


async def test_build_errors_suppress_follow_on_type_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _routed_hal_config()
    build_errors = {
        uid: BuildError(uid=uid, error_type="import", message="driver unavailable") for uid in config.device_uids
    }
    rig = _FakeRig(build_errors=build_errors)
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()

    assert rig.opened
    assert rig.closed
    assert {violation.code for violation in raised.value.violations} == {"build.import"}
    assert {violation.loc[-1] for violation in raised.value.violations} == config.device_uids


async def test_optical_routing_selector_must_be_a_discrete_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _routed_hal_config()
    unavailable = config.device_uids - {"selector"}
    build_errors = {uid: BuildError(uid=uid, error_type="import", message="driver unavailable") for uid in unavailable}
    rig = _FakeRig(
        devices={"selector": _handle("selector", "unsupported")},
        build_errors=build_errors,
    )
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()

    routing_violations = [
        violation
        for violation in raised.value.violations
        if violation.code == "hal.optical_routing.selector.not_discrete_axis"
    ]
    assert len(routing_violations) == 1
    assert routing_violations[0].loc == ("hal", "optical_routing")
    assert "selector" in routing_violations[0].msg


async def test_runtime_compatibility_errors_close_the_rig(monkeypatch: pytest.MonkeyPatch) -> None:
    hal = HAL(_hal_config())
    rig = _FakeRig()
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()

    assert rig.closed
    assert {violation.code for violation in raised.value.violations} == {
        "hal.detection.not_camera",
        "hal.filter_wheel.not_discrete_axis",
        "hal.illumination.not_laser",
        "hal.stage.not_continuous_axis",
    }


async def test_interface_failures_are_collected_without_cascading(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _hal_config()
    devices = {uid: _handle(uid, interface_error=RuntimeError("interface unavailable")) for uid in config.device_uids}
    rig = _FakeRig(devices=devices)
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()

    assert rig.closed
    assert {violation.code for violation in raised.value.violations} == {"hal.device.interface"}
    assert {violation.loc[-1] for violation in raised.value.violations} == config.device_uids


async def test_camera_geometry_transport_failures_are_collected_and_close_the_rig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _hal_config()
    config = config.model_copy(
        update={
            "devices": {**config.devices, "camera_b": config.devices["camera"]},
            "detection": {
                **config.detection,
                "camera_b": DetectionAssembly(filter_wheels=[], magnification=1, rotation_deg=0),
            },
        }
    )
    cameras = {
        "camera": _handle("camera", property_error=RuntimeError("first failure")),
        "camera_b": _handle("camera_b", property_error=RuntimeError("second failure")),
    }
    rig = _FakeRig(
        devices=dict(cameras),
        build_errors={
            uid: BuildError(uid=uid, error_type="import", message="unavailable")
            for uid in config.device_uids - cameras.keys()
        },
    )
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()
    violations = [v for v in raised.value.violations if v.code == "hal.camera.geometry"]
    assert rig.closed
    assert {v.code for v in raised.value.violations} == {"build.import", "hal.camera.geometry"}
    assert {v.loc[-1] for v in violations} == {"camera", "camera_b"}
    assert any("first failure" in v.msg for v in violations)
    assert any("second failure" in v.msg for v in violations)
    for camera in cameras.values():
        cast("AsyncMock", camera.props.get).assert_awaited_once_with("pixel_size_um", "sensor_size_px")


async def test_camera_geometry_reports_failed_and_missing_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _hal_config()
    camera = _handle(
        "camera",
        properties=PropResults(
            results={
                "pixel_size_um": Result[PropertyModel].err("pixel size unavailable"),
            }
        ),
    )
    rig = _FakeRig(
        devices={"camera": camera},
        build_errors={
            uid: BuildError(uid=uid, error_type="import", message="unavailable")
            for uid in config.device_uids - {"camera"}
        },
    )
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(HALStartupError) as raised:
        await hal.open()
    assert rig.closed
    assert {v.code for v in raised.value.violations} == {"build.import", "hal.camera.geometry"}
    assert {v.loc for v in raised.value.violations if v.code == "hal.camera.geometry"} == {
        ("hal", "devices", "camera", "pixel_size_um"),
        ("hal", "devices", "camera", "sensor_size_px"),
    }

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from vxl_catalog import Catalog, FileCatalogBackend

from rigup import (
    BuildConfig,
    BuildError,
    CommandRequest,
    DeviceHandle,
    DeviceInterface,
    PropertyModel,
    PropResults,
    Result,
)
from vxl.errors import StartupError, Violation
from vxl.instrument import AcquisitionMode, Instrument, InstrumentConfig, InstrumentState
from vxl.instrument.core import Channel
from vxl.instrument.hal import HAL
from vxl.instrument.state import AcquisitionTask, FixedOpticalRoutingPolicy, SplitOpticalRoutingPolicy
from vxl.instrument.topology import (
    DetectionAssemblyConfig,
    HALConfig,
    IlluminationAssemblyConfig,
    OpticalRouteConfig,
    OpticalRoutingConfig,
    StageConfig,
)
from vxlib import Cell


def _catalog(tmp_path: Path) -> Catalog:
    return Catalog(
        FileCatalogBackend(tmp_path / "catalog"),
        resolve_root=lambda _spec: tmp_path / "acquisitions",
    )


async def _device_property(instrument: Instrument, device_id: str, name: str) -> Any:
    results = await instrument.get_device_properties(device_id, [name])
    return results[name].unwrap().value


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


class _InterfaceFailureHandle:
    async def interface(self) -> DeviceInterface:
        raise RuntimeError("interface unavailable")


class _InterfaceHandle:
    def __init__(self, uid: str, device_type: str) -> None:
        self._interface = DeviceInterface(uid=uid, type=device_type, commands={}, properties={})

    async def interface(self) -> DeviceInterface:
        return self._interface


class _FailingProperties:
    def __init__(self, message: str) -> None:
        self._message = message
        self.requested: tuple[str, ...] = ()

    async def get(self, *properties: str) -> None:
        self.requested = properties
        raise RuntimeError(self._message)


class _CameraWithFailingProperties:
    def __init__(self, message: str) -> None:
        self.props = _FailingProperties(message)

    async def close_preview_updates(self) -> None:
        pass


class _ResultProperties:
    def __init__(self, results: PropResults) -> None:
        self._results = results

    async def get(self, *_properties: str) -> PropResults:
        return self._results


class _CameraWithResultProperties:
    def __init__(self, results: PropResults) -> None:
        self.props = _ResultProperties(results)

    async def close_preview_updates(self) -> None:
        pass


class _FakeHAL:
    def __init__(self) -> None:
        self.cameras: dict[str, Any] = {}
        self.devices: dict[str, Any] = {}
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True


class _FakeFov:
    def clear_triggers(self) -> None:
        pass


class _FakeRoutingUpdates:
    async def close(self) -> None:
        pass


class _FailsAfterHALOpen(Instrument):
    async def _validate_startup(self) -> None:
        pass

    def _build_channels(self) -> dict[str, Channel]:
        raise RuntimeError("channel initialization failed")


class _FailsInstrumentValidation(Instrument):
    async def _startup_violations(self) -> list[Violation]:
        return [Violation(code="test.startup", msg="instrument validation failed")]


class _FakeBench:
    def __init__(self, value: InstrumentState) -> None:
        self.value = value


class _FakeSignalGenerator:
    async def get_ports(self) -> dict[str, str]:
        return {"camera_1": "ao0", "aotf_1": "ao1"}


class _FakeAxis:
    def __init__(self, lower: float, upper: float) -> None:
        self.lower = lower
        self.upper = upper

    async def get_lower_limit(self) -> float:
        return self.lower

    async def get_upper_limit(self) -> float:
        return self.upper


class _FakeStage:
    def __init__(self) -> None:
        self.x = _FakeAxis(0, 100)
        self.y = _FakeAxis(0, 100)
        self.z = _FakeAxis(0, 100)


class _FakeInstrumentHAL:
    def __init__(self, interfaces: dict[str, DeviceInterface]) -> None:
        self.devices = {
            uid: cast("Any", _InterfaceHandle(uid, interface.type)) for uid, interface in interfaces.items()
        }
        for uid, interface in interfaces.items():
            self.devices[uid]._interface = interface
        self.signal_generators = {"daq": cast("Any", _FakeSignalGenerator())}
        self.stage = _FakeStage()


def _hal_config() -> HALConfig:
    uids = {"camera", "laser", "x", "y", "z", "filter"}
    devices = {uid: BuildConfig(target="builtins.object") for uid in uids}
    return HALConfig(
        devices=devices,
        stage=StageConfig(x="x", y="y", z="z"),
        detection={
            "camera": DetectionAssemblyConfig(
                filter_wheels=["filter"],
                magnification=1,
                rotation_deg=0,
            )
        },
        illumination={"laser": IlluminationAssemblyConfig()},
    )


def _routed_hal_config() -> HALConfig:
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
            "illumination": {"laser": IlluminationAssemblyConfig(routing={"excitation_side": ["left", "right"]})},
            "optical_routing": OpticalRoutingConfig(
                {
                    "excitation_side": {
                        "left": OpticalRouteConfig({"selector": "left"}),
                        "right": OpticalRouteConfig({"selector": "right"}),
                    }
                }
            ),
        }
    )


def test_violation_serializes_for_api_responses() -> None:
    violation = Violation(
        code="build.import",
        msg="Device failed to import",
        loc=("hal", "devices", "camera"),
    )

    assert violation.model_dump(mode="json") == {
        "code": "build.import",
        "msg": "Device failed to import",
        "loc": ["hal", "devices", "camera"],
    }


def test_startup_error_formats_a_terminal_report() -> None:
    error = StartupError(
        [
            Violation(
                code="build.import",
                msg="Driver unavailable",
                loc=("hal", "devices", "camera"),
            ),
            Violation(msg="No usable stage"),
        ]
    )

    assert str(error) == (
        "Instrument startup failed:\n  - [build.import] hal.devices.camera: Driver unavailable\n  - No usable stage"
    )


async def test_build_errors_suppress_follow_on_type_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _routed_hal_config()
    build_errors = {
        uid: BuildError(uid=uid, error_type="import", message="driver unavailable") for uid in config.device_uids
    }
    rig = _FakeRig(build_errors=build_errors)
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(StartupError) as raised:
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
        devices={"selector": cast("Any", _InterfaceHandle("selector", "unsupported"))},
        build_errors=build_errors,
    )
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(StartupError) as raised:
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

    with pytest.raises(StartupError) as raised:
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
    devices = {uid: cast("Any", _InterfaceFailureHandle()) for uid in config.device_uids}
    rig = _FakeRig(devices=devices)
    hal = HAL(config)
    monkeypatch.setattr(hal, "_rig", rig)

    with pytest.raises(StartupError) as raised:
        await hal.open()

    assert rig.closed
    assert {violation.code for violation in raised.value.violations} == {"hal.device.interface"}
    assert {violation.loc[-1] for violation in raised.value.violations} == config.device_uids


async def test_camera_geometry_transport_failures_are_collected_and_close_the_rig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = _FakeRig()
    hal = HAL(_hal_config())
    monkeypatch.setattr(hal, "_rig", rig)
    camera_a = _CameraWithFailingProperties("first failure")
    camera_b = _CameraWithFailingProperties("second failure")

    async def inspect_devices() -> tuple[list[Violation], set[str]]:
        hal.cameras.update(
            {
                "camera_a": cast("Any", camera_a),
                "camera_b": cast("Any", camera_b),
            }
        )
        return [], set()

    monkeypatch.setattr(hal, "_inspect_devices", inspect_devices)
    monkeypatch.setattr(hal, "_compatibility_violations", lambda _: [])

    with pytest.raises(StartupError) as raised:
        await hal.open()

    assert rig.closed
    assert {violation.code for violation in raised.value.violations} == {"hal.camera.geometry"}
    assert {violation.loc[-1] for violation in raised.value.violations} == {"camera_a", "camera_b"}
    assert camera_a.props.requested == ("pixel_size_um", "sensor_size_px")
    assert camera_b.props.requested == ("pixel_size_um", "sensor_size_px")


async def test_camera_geometry_reports_failed_and_missing_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = _FakeRig()
    hal = HAL(_hal_config())
    monkeypatch.setattr(hal, "_rig", rig)
    camera = _CameraWithResultProperties(
        PropResults(
            results={
                "pixel_size_um": Result[PropertyModel].err("pixel size unavailable"),
            }
        )
    )

    async def inspect_devices() -> tuple[list[Violation], set[str]]:
        hal.cameras["camera"] = cast("Any", camera)
        return [], set()

    monkeypatch.setattr(hal, "_inspect_devices", inspect_devices)
    monkeypatch.setattr(hal, "_compatibility_violations", lambda _: [])

    with pytest.raises(StartupError) as raised:
        await hal.open()

    assert {violation.loc for violation in raised.value.violations} == {
        ("hal", "devices", "camera", "pixel_size_um"),
        ("hal", "devices", "camera", "sensor_size_px"),
    }
    assert {violation.code for violation in raised.value.violations} == {"hal.camera.geometry"}


async def test_instrument_startup_failure_closes_open_hal() -> None:
    instrument = cast("Any", object.__new__(_FailsAfterHALOpen))
    hal = _FakeHAL()
    instrument._lock = asyncio.Lock()
    instrument._hal = hal
    instrument._channels = {}
    instrument._preview_channels = []
    instrument._preview_unsubs = []
    instrument._routing_updates = _FakeRoutingUpdates()
    instrument._routing_unsubs = []
    instrument._mode = Cell(AcquisitionMode.IDLE)
    instrument.fov = _FakeFov()

    with pytest.raises(RuntimeError, match="channel initialization failed"):
        await instrument.open()

    assert hal.opened
    assert hal.closed


async def test_instrument_validation_failure_closes_open_hal() -> None:
    instrument = cast("Any", object.__new__(_FailsInstrumentValidation))
    hal = _FakeHAL()
    instrument._lock = asyncio.Lock()
    instrument._hal = hal
    instrument._channels = {}
    instrument._preview_channels = []
    instrument._preview_unsubs = []
    instrument._routing_updates = _FakeRoutingUpdates()
    instrument._routing_unsubs = []
    instrument._mode = Cell(AcquisitionMode.IDLE)
    instrument.fov = _FakeFov()

    with pytest.raises(StartupError, match="instrument validation failed"):
        await instrument.open()

    assert hal.opened
    assert hal.closed


async def test_instrument_startup_collects_profile_port_and_stage_violations() -> None:
    config = InstrumentConfig.read(Path("src/vxl/_templates/simulated-local.voxel.yaml"))
    state = InstrumentState(**config.default.model_dump())
    profile = state.imaging.profiles["single_gfp"]
    profile = profile.model_copy(
        update={
            "sync": {**profile.sync, "camera_1": profile.sync["daq"]},
            "props": {
                "camera_1": {"temperature": -20, "missing": 1},
                "unavailable": {"gain": 1},
            },
            "setup": {
                "camera_1": [CommandRequest(attr="missing_command")],
                "unavailable": [CommandRequest(attr="configure")],
            },
        }
    )
    imaging = state.imaging.model_copy(update={"profiles": {**state.imaging.profiles, "single_gfp": profile}})
    state = state.model_copy(
        update={
            "imaging": imaging,
            "tasks": {"outside": AcquisitionTask(x=101, y=50, start=-1, end=50, profile_ids=["single_gfp"])},
        }
    )
    camera_interface = DeviceInterface.model_validate(
        {
            "uid": "camera_1",
            "type": "camera",
            "commands": {},
            "properties": {
                "temperature": {
                    "name": "temperature",
                    "label": "Temperature",
                    "dtype": "float",
                    "access": "ro",
                }
            },
        }
    )
    daq_interface = DeviceInterface(uid="daq", type="signal_generator", commands={}, properties={})
    instrument = cast("Any", object.__new__(Instrument))
    instrument._bench = _FakeBench(state)
    instrument._hal = _FakeInstrumentHAL({"camera_1": camera_interface, "daq": daq_interface})

    violations = await instrument._startup_violations()

    assert {violation.code for violation in violations} == {
        "bench.stage_position.out_of_bounds",
        "imaging.profile.props.device_unavailable",
        "imaging.profile.props.property_missing",
        "imaging.profile.props.property_read_only",
        "imaging.profile.setup.command_missing",
        "imaging.profile.setup.device_unavailable",
        "imaging.profile.sync.not_signal_generator",
        "imaging.profile.sync.port_missing",
    }
    assert {violation.loc for violation in violations if violation.code == "bench.stage_position.out_of_bounds"} == {
        ("bench", "tasks", "outside", "x"),
        ("bench", "tasks", "outside", "start"),
        ("bench", "stencil", "z_end"),
    }


async def test_simulated_instrument_passes_runtime_startup_validation(tmp_path: Path) -> None:
    config = InstrumentConfig.read(Path("src/vxl/_templates/simulated-local.voxel.yaml"))
    instrument = Instrument.from_path(
        config.instantiate("runtime-validation", tmp_path),
        catalog=_catalog(tmp_path),
    )

    try:
        await instrument.open()
        positions: list[float] = []
        arrived = asyncio.Event()

        def observe_position(update: tuple[str, PropResults]) -> None:
            device_id, results = update
            position = results.results.get("position")
            if device_id != "x_axis" or position is None or not position.is_ok:
                return
            value = float(position.unwrap().value)
            positions.append(value)
            if value == 1:
                arrived.set()

        unsubscribe = instrument.device_property_updates.subscribe(observe_position)
        await instrument.move_stage(x=1, wait=True)
        await asyncio.wait_for(arrived.wait(), timeout=1)
        unsubscribe()

        assert await _device_property(instrument, "x_axis", "position") == 1
        assert positions[-1] == 1

        assert instrument.routing_targets.value == {"excitation_side": "left"}
        assert await _device_property(instrument, "illumination_side_selector", "label") == "left"

        await instrument.override_optical_route("excitation_side", "right")
        assert await _device_property(instrument, "illumination_side_selector", "label") == "right"
        assert instrument.routing_targets.value == {"excitation_side": "left"}

        await instrument.apply_optical_routing()
        assert await _device_property(instrument, "illumination_side_selector", "label") == "left"

        await instrument.update_optical_routing_policy(
            "excitation_side",
            SplitOpticalRoutingPolicy(
                type="split",
                axis="x",
                threshold=1,
                lower="left",
                upper="right",
            ),
        )
        await instrument.add_tasks([(1, 0)])
        assert instrument.task_tiles.value[0].routes == {"excitation_side": "right"}

        await instrument.update_optical_routing_policy(
            "excitation_side",
            FixedOpticalRoutingPolicy(type="fixed", route="right"),
        )
        assert instrument.routing_targets.value == {"excitation_side": "right"}
        await instrument.apply_optical_routing()
        assert await _device_property(instrument, "illumination_side_selector", "label") == "right"
    finally:
        await instrument.close()


async def test_instrument_close_awaits_coalescer_workers(tmp_path: Path) -> None:
    config = InstrumentConfig.read(Path("src/vxl/_templates/simulated-local.voxel.yaml"))
    instrument = Instrument.from_path(
        config.instantiate("coalescer-cleanup", tmp_path),
        catalog=_catalog(tmp_path),
    )

    await instrument.open()
    try:
        instrument._routing_updates.update({})
        await asyncio.sleep(0)
        workers = [
            task
            for task in asyncio.all_tasks()
            if not task.done() and getattr(task.get_coro(), "__qualname__", "") == "Coalescer._run"
        ]
        assert workers
    finally:
        await instrument.close()

    remaining = [
        task
        for task in asyncio.all_tasks()
        if not task.done() and getattr(task.get_coro(), "__qualname__", "") == "Coalescer._run"
    ]
    assert not remaining


async def test_live_split_routing_uses_fov_hysteresis(tmp_path: Path) -> None:
    config = InstrumentConfig.read(Path("src/vxl/_templates/simulated-local.voxel.yaml"))
    x_axis = config.hal.devices["x_axis"]
    hal = config.hal.model_copy(
        update={
            "devices": {
                **config.hal.devices,
                "x_axis": x_axis.model_copy(update={"init": {**x_axis.init, "speed": 1_000_000}}),
            }
        }
    )
    default = config.default.model_copy(
        update={
            "routing": {
                "excitation_side": SplitOpticalRoutingPolicy(
                    type="split",
                    axis="x",
                    threshold=10_000,
                    lower="left",
                    upper="right",
                )
            }
        }
    )
    instrument = Instrument.from_path(
        config.model_copy(update={"hal": hal, "default": default}).instantiate("split-routing", tmp_path),
        catalog=_catalog(tmp_path),
    )

    async def wait_for_target(route: str) -> None:
        if instrument.routing_targets.value.get("excitation_side") == route:
            return
        arrived = asyncio.Event()
        unsubscribe = instrument.routing_targets.subscribe(
            lambda routes: arrived.set() if routes.get("excitation_side") == route else None
        )
        try:
            await asyncio.wait_for(arrived.wait(), timeout=1)
        finally:
            unsubscribe()

    async def wait_for_selector(route: str) -> None:
        arrived = asyncio.Event()

        def observe_properties(update: tuple[str, PropResults]) -> None:
            device_id, results = update
            if device_id != "illumination_side_selector":
                return
            label = results.results.get("label")
            if label is not None and label.is_ok and label.unwrap().value == route:
                arrived.set()

        unsubscribe = instrument.device_property_updates.subscribe(observe_properties)
        try:
            if await _device_property(instrument, "illumination_side_selector", "label") == route:
                arrived.set()
            await asyncio.wait_for(arrived.wait(), timeout=1)
        finally:
            unsubscribe()

    try:
        await instrument.open()
        fov = instrument.fov.cache
        if fov is None:
            pytest.fail("Instrument startup did not resolve the field of view")
        margin = fov[0] / 2

        assert instrument.routing_targets.value == {"excitation_side": "left"}
        await instrument.move_stage(x=10_000 + margin - 1, wait=True)
        await asyncio.sleep(0.1)
        assert instrument.routing_targets.value == {"excitation_side": "left"}

        await instrument.move_stage(x=10_000 + margin + 1, wait=True)
        await wait_for_target("right")
        await wait_for_selector("right")

        await instrument.move_stage(x=10_000, wait=True)
        await asyncio.sleep(0.1)
        assert instrument.routing_targets.value == {"excitation_side": "right"}

        await instrument.move_stage(x=10_000 - margin - 1, wait=True)
        await wait_for_target("left")
        await wait_for_selector("left")
    finally:
        await instrument.close()

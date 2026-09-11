"""Microscope hardware runtime and typed device inventory."""

import asyncio
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from rigup import DeviceHandle, DeviceInterface, Rig
from vxl.devices.axes import ContinuousAxisHandle
from vxl.devices.axes.discrete.handle import DiscreteAxisHandle
from vxl.devices.camera import CameraHandle
from vxl.devices.daq.clocked import SignalGeneratorHandle

from .errors import HALError, HALStartupError, Violation, ViolationLoc
from .topology import HardwareTopology, OpticalRouteDefinition

logger = logging.getLogger(__name__)

_CAMERA_GEOMETRY_PROPERTIES = ("pixel_size_um", "sensor_size_px")


@dataclass(frozen=True)
class Stage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.z


@dataclass(frozen=True)
class RouteDimension:
    """Observe and select hardware routes; rule evaluation and acquisition belong to Instrument."""

    uid: str
    selectors: Mapping[str, DiscreteAxisHandle]
    _definitions: Mapping[str, OpticalRouteDefinition]

    async def select(self, route: str) -> None:
        """Select and verify a route, awaiting every selector and reporting all ordinary failures."""
        definition = self._definitions.get(route)
        if definition is None:
            raise HALError(f"No optical route '{self.uid}.{route}'")
        # Resolve every handle before issuing any movement.
        selections = [(uid, self.selectors[uid], position) for uid, position in definition.root.items()]

        async def select_and_verify(handle: DiscreteAxisHandle, position: str) -> None:
            await handle.select(position, wait=True)
            actual = await self._read_position(handle)
            if actual != position:
                raise HALError(f"Selector did not settle at {position!r}; settled label is {actual!r}")

        results = await asyncio.gather(
            *(select_and_verify(handle, position) for _, handle, position in selections),
            return_exceptions=True,
        )
        errors: list[Exception] = []
        for (uid, _, _), result in zip(selections, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                result.add_note(f"Routing dimension '{self.uid}', selector '{uid}'")
                errors.append(result)
        if errors:
            raise ExceptionGroup(f"Routing selection failed for '{self.uid}'", errors)

    async def current_route(self) -> str | None:
        """Read selectors now; return a route only when stationary and uniquely matched.

        Moving or unlabeled selectors and ambiguous/unmatched positions return
        ``None``. Read failures propagate instead of using stale cached values.
        """
        labels = await asyncio.gather(*(self._read_position(handle) for handle in self.selectors.values()))
        if any(label is None for label in labels):
            return None
        positions = dict(zip(self.selectors, labels, strict=True))
        matches = [
            name
            for name, route in self._definitions.items()
            if all(positions[uid] == position for uid, position in route.root.items())
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    async def _read_position(handle: DiscreteAxisHandle) -> str | None:
        """Read movement before label in one device request; expose only a settled label."""
        props = await handle.props.get("is_moving", "label")
        moving = props["is_moving"].unwrap().value
        label = props["label"].unwrap().value
        return label if moving is False and isinstance(label, str) else None


class HAL:
    """Runtime hardware abstraction: opens the rig and exposes typed device handles."""

    def __init__(self, topology: HardwareTopology, name: str = "VoxelHAL") -> None:
        self._topology = topology
        self._rig = Rig(topology, name)

        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DiscreteAxisHandle] = {}
        self.fws: dict[str, DiscreteAxisHandle] = {}
        self.routing: dict[str, RouteDimension] = {}
        self.signal_generators: dict[str, SignalGeneratorHandle] = {}
        self._device_interfaces: dict[str, DeviceInterface] = {}
        self._stage: Stage | None = None

    @property
    def topology(self) -> HardwareTopology:
        return self._topology

    @property
    def rig(self) -> Rig:
        return self._rig

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return self.rig.devices

    @property
    def device_interfaces(self) -> Mapping[str, DeviceInterface]:
        """Interfaces retained from the successful startup inspection."""
        return dict(self._device_interfaces)

    @property
    def stage(self) -> Stage:
        if self._stage is None:
            raise RuntimeError("HAL is not open — stage is unavailable")
        return self._stage

    async def open(self) -> None:
        violations: list[Violation] = []
        try:
            await self._rig.open()
            violations.extend(self._build_violations())
            interface_violations, interface_unavailable = await self._inspect_and_classify_devices()
            violations.extend(interface_violations)
            unavailable = set(self.rig.build_errors) | interface_unavailable
            violations.extend(self._compatibility_violations(unavailable))
            property_violations = await asyncio.gather(
                self._camera_geometry_violations(),
                self._stage_limit_violations(),
                self._signal_port_violations(),
            )
            for group in property_violations:
                violations.extend(group)
            if not violations:
                self._resolve_stage()
                self._resolve_routing()
        except BaseException:
            await self.close()
            raise
        if violations:
            await self.close()
            raise HALStartupError(violations)

    async def close(self) -> None:
        self._stage = None
        self.routing.clear()
        self._device_interfaces = {}
        await asyncio.gather(*(camera.close_preview_updates() for camera in self.cameras.values()))
        self.cameras.clear()
        self.lasers.clear()
        self.aotfs.clear()
        self.continuous_axes.clear()
        self.discrete_axes.clear()
        self.fws.clear()
        self.signal_generators.clear()
        await self._rig.close()

    def _build_violations(self) -> list[Violation]:
        return [
            Violation(
                code=f"build.{error.error_type}",
                msg=f"Device '{uid}' failed to build: {error.message}",
                loc=("hal", "devices", uid),
            )
            for uid, error in self.rig.build_errors.items()
        ]

    async def _inspect_and_classify_devices(self) -> tuple[list[Violation], set[str]]:
        """Inspect and classify every built device, collecting independent interface failures."""
        devices = list(self.rig.devices.items())
        interfaces = await asyncio.gather(
            *(handle.interface() for _, handle in devices),
            return_exceptions=True,
        )
        violations = []
        unavailable = set()
        for (uid, handle), interface in zip(devices, interfaces, strict=True):
            if isinstance(interface, BaseException):
                if not isinstance(interface, Exception):
                    raise interface
                unavailable.add(uid)
                violations.append(
                    Violation(
                        code="hal.device.interface",
                        msg=f"Unable to inspect device '{uid}': {interface}",
                        loc=("hal", "devices", uid),
                    )
                )
                continue

            self._device_interfaces[uid] = interface

            match interface.type:
                case "camera":
                    self.cameras[uid] = CameraHandle.wrap(handle)
                case "signal_generator":
                    self.signal_generators[uid] = SignalGeneratorHandle.wrap(handle)
                case "laser":
                    self.lasers[uid] = handle
                case "aotf":
                    self.aotfs[uid] = handle
                case "continuous_axis":
                    self.continuous_axes[uid] = ContinuousAxisHandle.wrap(handle)
                case "discrete_axis":
                    self.discrete_axes[uid] = DiscreteAxisHandle.wrap(handle)
                case _:
                    logger.debug("Uncategorized device '%s' of type '%s'", uid, interface.type)

        self.fws.update(
            (uid, self.discrete_axes[uid]) for uid in self._topology.filter_wheels if uid in self.discrete_axes
        )
        return violations, unavailable

    async def _camera_geometry_violations(self) -> list[Violation]:
        """Read the camera geometry required at startup, collecting transport and property failures."""
        cameras = list(self.cameras.items())
        results = await asyncio.gather(
            *(camera.props.get(*_CAMERA_GEOMETRY_PROPERTIES) for _, camera in cameras),
            return_exceptions=True,
        )
        violations = []
        for (uid, _), result in zip(cameras, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="hal.camera.geometry",
                        msg=f"Unable to read camera geometry for '{uid}': {result}",
                        loc=("hal", "devices", uid),
                    )
                )
                continue

            for property_name in _CAMERA_GEOMETRY_PROPERTIES:
                if property_name not in result:
                    violations.append(
                        Violation(
                            code="hal.camera.geometry",
                            msg=f"Camera '{uid}' did not return required property '{property_name}'.",
                            loc=("hal", "devices", uid, property_name),
                        )
                    )
                    continue
                property_result = result[property_name]
                if property_result.is_ok:
                    continue
                try:
                    property_result.unwrap()
                except RuntimeError as exc:
                    violations.append(
                        Violation(
                            code="hal.camera.geometry",
                            msg=f"Unable to read required camera property '{property_name}' for '{uid}': {exc}",
                            loc=("hal", "devices", uid, property_name),
                        )
                    )
        return violations

    async def _stage_limit_violations(self) -> list[Violation]:
        """Read and validate assigned stage bounds without depending on instrument state."""
        stage = self._topology.stage
        requests = []
        for axis, uid in (("x", stage.x), ("y", stage.y), ("z", stage.z)):
            # Build, interface, and role validation already report unavailable/incorrect axes.
            if (handle := self.continuous_axes.get(uid)) is not None:
                requests.extend(((axis, "lower", handle.get_lower_limit()), (axis, "upper", handle.get_upper_limit())))
        results = await asyncio.gather(*(request for _, _, request in requests), return_exceptions=True)
        limits: dict[str, dict[str, float]] = {}
        violations = []
        for (axis, bound, _), result in zip(requests, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="hal.stage.limit_unavailable",
                        msg=f"Unable to read the {axis}-axis {bound} limit: {result}",
                        loc=("hal", "stage", axis, bound),
                    )
                )
            else:
                limits.setdefault(axis, {})[bound] = result

        for axis, bounds in limits.items():
            if "lower" not in bounds or "upper" not in bounds:
                continue
            lower, upper = bounds["lower"], bounds["upper"]
            if lower > upper:
                violations.append(
                    Violation(
                        code="hal.stage.limits_invalid",
                        msg=f"The {axis}-axis lower limit ({lower}) exceeds its upper limit ({upper}).",
                        loc=("hal", "stage", axis),
                    )
                )
        return violations

    async def _signal_port_violations(self) -> list[Violation]:
        """Discover every signal generator's ports into its shared property cache."""
        uids = sorted(self.signal_generators)
        results = await asyncio.gather(
            *(self.signal_generators[uid].get_ports() for uid in uids),
            return_exceptions=True,
        )
        violations = []
        for uid, result in zip(uids, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                violations.append(
                    Violation(
                        code="hal.signal_generator.ports",
                        msg=f"Unable to read ports for signal generator '{uid}': {result}",
                        loc=("hal", "devices", uid, "ports"),
                    )
                )
        return violations

    def _compatibility_violations(self, unavailable: set[str]) -> list[Violation]:
        """Return all role and topology conflicts detectable from the built device inventory."""
        return [
            *self._camera_path_violations(unavailable),
            *self._laser_path_violations(unavailable),
            *self._stage_violations(unavailable),
            *self._filter_wheel_violations(unavailable),
            *self._routing_selector_violations(unavailable),
            *self._aux_reserved_violations(),
        ]

    def _resolve_stage(self) -> None:
        """Publish composite runtime handles after every startup check succeeds."""
        self._stage = Stage(
            x=self.continuous_axes[self._topology.stage.x],
            y=self.continuous_axes[self._topology.stage.y],
            z=self.continuous_axes[self._topology.stage.z],
        )

    def _resolve_routing(self) -> None:
        self.routing = {
            uid: RouteDimension(
                uid=uid,
                selectors={
                    selector: self.discrete_axes[selector] for route in definitions.values() for selector in route.root
                },
                _definitions=definitions,
            )
            for uid, definitions in self._topology.optical_routing.root.items()
        }

    def _camera_path_violations(self, unavailable: set[str]) -> list[Violation]:
        violations = []
        camera_ids = set(self.cameras.keys())
        detection_ids = set(self._topology.detection.keys())
        if missing := camera_ids - detection_ids:
            violations.append(
                Violation(
                    code="hal.camera.missing_detection_path",
                    msg=f"Cameras without detection paths: {missing}",
                    loc=("hal", "detection"),
                )
            )
        if invalid := detection_ids - camera_ids - unavailable:
            violations.append(
                Violation(
                    code="hal.detection.not_camera",
                    msg=f"Detection paths referencing non-camera devices: {invalid}",
                    loc=("hal", "detection"),
                )
            )
        return violations

    def _laser_path_violations(self, unavailable: set[str]) -> list[Violation]:
        violations = []
        laser_ids = set(self.lasers.keys())
        illumination_ids = set(self._topology.illumination.keys())
        if missing := laser_ids - illumination_ids:
            violations.append(
                Violation(
                    code="hal.laser.missing_illumination_path",
                    msg=f"Lasers without illumination paths: {missing}",
                    loc=("hal", "illumination"),
                )
            )
        if invalid := illumination_ids - laser_ids - unavailable:
            violations.append(
                Violation(
                    code="hal.illumination.not_laser",
                    msg=f"Illumination paths referencing non-laser devices: {invalid}",
                    loc=("hal", "illumination"),
                )
            )
        return violations

    def _stage_violations(self, unavailable: set[str]) -> list[Violation]:
        stage_cfg = self._topology.stage
        if invalid := {stage_cfg.x, stage_cfg.y, stage_cfg.z} - set(self.continuous_axes.keys()) - unavailable:
            return [
                Violation(
                    code="hal.stage.not_continuous_axis",
                    msg=f"Stage axes are not continuous_axis devices: {invalid}",
                    loc=("hal", "stage"),
                )
            ]
        return []

    def _filter_wheel_violations(self, unavailable: set[str]) -> list[Violation]:
        return self._discrete_axis_role_violations(
            self._topology.filter_wheels,
            unavailable,
            code="hal.filter_wheel.not_discrete_axis",
            label="Filter wheels",
            loc=("hal", "detection"),
        )

    def _routing_selector_violations(self, unavailable: set[str]) -> list[Violation]:
        selectors = {
            selector_uid
            for routes in self._topology.optical_routing.root.values()
            for route in routes.values()
            for selector_uid in route.root
        }
        return self._discrete_axis_role_violations(
            selectors,
            unavailable,
            code="hal.optical_routing.selector.not_discrete_axis",
            label="Optical-routing selectors",
            loc=("hal", "optical_routing"),
        )

    def _discrete_axis_role_violations(
        self,
        configured: Collection[str],
        unavailable: set[str],
        *,
        code: str,
        label: str,
        loc: ViolationLoc,
    ) -> list[Violation]:
        if invalid := set(configured) - self.discrete_axes.keys() - unavailable:
            return [
                Violation(
                    code=code,
                    msg=f"{label} are not discrete_axis devices: {invalid}",
                    loc=loc,
                )
            ]
        return []

    def _aux_reserved_violations(self) -> list[Violation]:
        # Centralized check for all aux devices across all paths
        reserved = (
            set(self.cameras.keys())
            | set(self.lasers.keys())
            | set(self._topology.filter_wheels)
            | {self._topology.stage.x, self._topology.stage.y, self._topology.stage.z}
            | set(self.signal_generators.keys())
        )

        violations = []
        path_groups = [("detection", self._topology.detection), ("illumination", self._topology.illumination)]
        for path_type, paths in path_groups:
            for path_id, path in paths.items():
                for aux in path.aux_devices:
                    if aux in reserved:
                        violations.append(
                            Violation(
                                code="hal.aux.reserved",
                                msg=f"Aux device '{aux}' in {path_type} path '{path_id}' is a reserved type.",
                                loc=("hal", path_type, path_id, "aux_devices"),
                            )
                        )
        return violations

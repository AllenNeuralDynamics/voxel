"""The hardware part of an instrument file, ``hal``: devices, nets, stage, light paths, routing and capture."""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, RootModel, SerializeAsAny, ValidationInfo, field_validator, model_validator
from rigup.config import DeviceConfig, DeviceUid, RigConfig
from vxlib.schema import FrozenModel, repeated

from .capture import CaptureSettings, Modality, PositionSync, Sweep, installed_capture_settings
from .identifiers import NetName, RouteName, RoutingDimension
from .nets import Net, split_pin
from .specimen import DetectionGeometry, SpecimenAxis, Stage
from .violations import Violation, ViolationLoc, assignment_violations, not_configured


class OpticalPath(FrozenModel):
    aux_devices: list[DeviceUid] = Field(default_factory=list)
    routing: set[RoutingDimension] = Field(default_factory=set)


class DetectionPath(OpticalPath):
    """The light path from the sample to 1 camera, keyed by the camera."""

    filter_wheels: list[DeviceUid] = Field(default_factory=list)
    geometry: DetectionGeometry

    @field_validator("filter_wheels")
    @classmethod
    def _unique_filter_wheels(cls, value: list[str]) -> list[str]:
        if duplicates := repeated(value):
            raise ValueError(f"filter wheels must be unique (duplicates: {duplicates})")
        return value


class IlluminationPath(OpticalPath):
    """The light path from 1 light source to the sample, keyed by the source."""


PositionLabel = Annotated[str, Field(min_length=1)]
"""The label of a slot of a discrete axis, such as a filter wheel position, as its device declares it."""

type DiscreteAxisPositions = dict[DeviceUid, PositionLabel]


class OpticalRouteDefinition(FrozenModel):
    """Selector positions and an optional display label for 1 optical route."""

    selectors: DiscreteAxisPositions = Field(min_length=1)
    label: str | None = None


class SelectRoutingDefinition(FrozenModel):
    """A dimension whose route is selected explicitly in instrument state."""

    type: Literal["select"]
    routes: dict[RouteName, OpticalRouteDefinition] = Field(min_length=1)


class SplitRoutingDefinition(FrozenModel):
    """A spatial split with config-owned axis and selector positions."""

    type: Literal["split-x", "split-y"]
    routes: dict[RouteName, OpticalRouteDefinition]

    @property
    def axis(self) -> Literal["x", "y"]:
        return "x" if self.type == "split-x" else "y"

    @model_validator(mode="after")
    def _check_sides(self) -> Self:
        if self.routes.keys() != {"lower", "upper"}:
            raise ValueError("split routing must define exactly 'lower' and 'upper' routes")
        if self.routes["lower"].selectors == self.routes["upper"].selectors:
            raise ValueError("split routing sides must define different selector positions")
        return self


type RoutingDefinition = Annotated[SelectRoutingDefinition | SplitRoutingDefinition, Field(discriminator="type")]


class OpticalRouting(RootModel[dict[RoutingDimension, RoutingDefinition]]):
    """Configured selection strategies and selector positions, keyed by dimension."""

    model_config = ConfigDict(frozen=True)


class HALConfig(RigConfig, frozen=True):
    """The hardware blueprint: the rig's devices and nodes, plus nets, stage, light paths, routing and capture.

    ``capture`` has exactly 1 key, the modality. Its value is validated with the settings model of that modality's
    CaptureEngine: from the validation context's ``capture_settings`` mapping when given, otherwise from the
    installed entry points.
    """

    nets: dict[DeviceUid, dict[NetName, Net]] = Field(default_factory=dict)
    stage: Stage
    detection: dict[DeviceUid, DetectionPath]
    illumination: dict[DeviceUid, IlluminationPath]
    optical_routing: OpticalRouting = Field(default_factory=lambda: OpticalRouting({}))
    capture: dict[Modality, SerializeAsAny[CaptureSettings]]

    @field_validator("capture", mode="before")
    @classmethod
    def _capture_settings(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, Mapping) or len(value) != 1:
            raise ValueError("capture has exactly 1 key: the modality")
        ((modality, settings),) = value.items()
        context = info.context if isinstance(info.context, Mapping) else {}
        models = context.get("capture_settings")
        if models is None:
            models = installed_capture_settings()
        model = models.get(modality)
        if model is None:
            raise ValueError(f"no CaptureEngine is installed for modality '{modality}' (installed: {sorted(models)})")
        return {modality: settings if isinstance(settings, model) else model.model_validate(settings)}

    @property
    def modality(self) -> Modality:
        return next(iter(self.capture))

    @property
    def capture_settings(self) -> CaptureSettings:
        return next(iter(self.capture.values()))

    @property
    def device_configs(self) -> dict[str, DeviceConfig]:
        configs = dict(self.devices)
        for node in self.nodes.values():
            configs.update(node.devices)
        return configs

    @property
    def device_uids(self) -> set[str]:
        return set(self.device_configs)

    @property
    def filter_wheels(self) -> set[str]:
        return {uid for path in self.detection.values() for uid in path.filter_wheels}

    def check_discrete_axis_positions(self, positions: DiscreteAxisPositions, *, loc: ViolationLoc) -> list[Violation]:
        """Check device references and position labels without importing device classes."""
        violations = []
        for device_uid, position in positions.items():
            device = self.device_configs.get(device_uid)
            if device is None:
                violations.append(
                    not_configured(
                        "Device",
                        device_uid,
                        code="discrete_axis.device_missing",
                        loc=(*loc, device_uid),
                    )
                )
                continue
            slots = device.init.get("slots")
            if not isinstance(slots, Mapping):
                violations.append(
                    Violation(
                        code="discrete_axis.positions_missing",
                        msg=f"Device '{device_uid}' does not declare discrete-axis positions.",
                        loc=(*loc, device_uid),
                    )
                )
                continue
            configured: set[str] = set()
            for slot in slots.values():
                if isinstance(slot, str):
                    configured.add(slot)
                elif isinstance(slot, Mapping) and isinstance(label := slot.get("label"), str):
                    configured.add(label)
            if position not in configured:
                violations.append(
                    Violation(
                        code="discrete_axis.position_missing",
                        msg=(
                            f"Position '{position}' is not configured for device '{device_uid}' "
                            f"(available: {sorted(configured)})."
                        ),
                        loc=(*loc, device_uid),
                    )
                )
        return violations

    def semantic_violations(self, *, loc: ViolationLoc = ("hal",)) -> list[Violation]:
        """Return every relationship in ``hal`` that the file alone shows cannot resolve.

        Checks that need device classes, such as their connectors, run where the classes are imported.
        """
        return [
            *self._reference_violations(loc),
            *self._net_violations(loc),
            *self._capture_violations(loc),
            *self._optical_routing_violations(loc),
        ]

    def _missing(self, uid: str, *, code: str, label: str, loc: ViolationLoc) -> list[Violation]:
        return [] if uid in self.device_uids else [not_configured(label, uid, code=code, loc=loc)]

    def _reference_violations(self, loc: ViolationLoc) -> list[Violation]:
        violations = []
        for axis, stage_axis in self.stage.axes().items():
            violations += self._missing(
                stage_axis.device, code="hal.stage.device_missing", label="Device", loc=(*loc, "stage", axis, "device")
            )
        for group, paths in (("detection", self.detection), ("illumination", self.illumination)):
            for path_id, path in paths.items():
                path_loc = (*loc, group, path_id)
                violations += self._missing(path_id, code=f"hal.{group}.device_missing", label="Device", loc=path_loc)
                for index, aux in enumerate(path.aux_devices):
                    violations += self._missing(
                        aux,
                        code=f"hal.{group}.aux_device_missing",
                        label="Device",
                        loc=(*path_loc, "aux_devices", index),
                    )
                if isinstance(path, DetectionPath):
                    for index, wheel in enumerate(path.filter_wheels):
                        violations += self._missing(
                            wheel,
                            code="hal.detection.filter_wheel_missing",
                            label="Filter wheel",
                            loc=(*path_loc, "filter_wheels", index),
                        )
        return violations

    def _net_violations(self, loc: ViolationLoc) -> list[Violation]:
        violations = []
        pin_owner: dict[str, tuple[str, str]] = {}

        def claim(pin: str, sender: str, name: str, pin_loc: ViolationLoc) -> None:
            if pin in pin_owner:
                first_sender, first_name = pin_owner[pin]
                violations.append(
                    Violation(
                        code="hal.nets.pin_shared",
                        msg=f"Pin '{pin}' is already in net '{first_sender}.{first_name}'.",
                        loc=pin_loc,
                    )
                )
            else:
                pin_owner[pin] = (sender, name)

        for sender, nets in self.nets.items():
            sender_loc = (*loc, "nets", sender)
            if sender not in self.device_uids:
                violations.append(not_configured("Device", sender, code="hal.nets.device_missing", loc=sender_loc))
                continue
            for name, net in nets.items():
                net_loc = (*sender_loc, name)
                claim(f"{sender}/{net.pin}", sender, name, (*net_loc, "pin"))
                for index, pin in enumerate(net.to):
                    pin_loc = (*net_loc, "to", index)
                    receiver, _ = split_pin(pin)
                    if receiver not in self.device_uids:
                        violations.append(
                            not_configured("Device", receiver, code="hal.nets.device_missing", loc=pin_loc)
                        )
                        continue
                    claim(pin, sender, name, pin_loc)
        return violations

    def _capture_violations(self, loc: ViolationLoc) -> list[Violation]:
        settings = self.capture_settings
        sender = settings.sender
        if not isinstance(settings.sync, PositionSync) or sender is None:
            return []
        sync_loc = (*loc, "capture", self.modality, "sync")
        if sender not in self.device_uids:
            return [not_configured("Device", sender, code="hal.capture.sender_missing", loc=sync_loc)]

        violations = []
        stage_devices: dict[str, SpecimenAxis] = {axis.device: name for name, axis in self.stage.axes().items()}
        axis = stage_devices.get(sender)
        if axis is None or not any(isinstance(m, Sweep) and m.axis == axis for m in settings.scan):
            violations.append(
                Violation(
                    code="hal.capture.position_sender_not_sweeping",
                    msg=f"A position sender must be the device of a sweep axis; '{sender}' is not.",
                    loc=sync_loc,
                )
            )
        if not any(net.to for net in self.nets.get(sender, {}).values()):
            violations.append(
                Violation(
                    code="hal.capture.sender_unwired",
                    msg=f"'{sender}' sends no net that reaches a receiver.",
                    loc=sync_loc,
                )
            )
        return violations

    def _optical_routing_violations(self, loc: ViolationLoc) -> list[Violation]:
        violations = []
        referenced: set[str] = set()
        for group, paths in (("detection", self.detection), ("illumination", self.illumination)):
            for path_id, path in paths.items():
                for dimension in path.routing:
                    if dimension in self.optical_routing.root:
                        referenced.add(dimension)
                    else:
                        violations.append(
                            not_configured(
                                "Routing dimension",
                                dimension,
                                code="hal.optical_routing.participation.dimension_missing",
                                loc=(*loc, group, path_id, "routing", dimension),
                            )
                        )

        selector_owners: dict[str, dict[str, str]] = {}
        for dimension, definition in self.optical_routing.root.items():
            if dimension not in referenced:
                violations.append(
                    Violation(
                        code="hal.optical_routing.dimension_unused",
                        msg=f"Routing dimension '{dimension}' is not used by any light path.",
                        loc=(*loc, "optical_routing", dimension),
                    )
                )
            routes_loc = (*loc, "optical_routing", dimension, "routes")
            first_route, first = next(iter(definition.routes.items()))
            for route, positions in definition.routes.items():
                selectors_loc = (*routes_loc, route, "selectors")
                if route != first_route:
                    violations += assignment_violations(
                        expected=first.selectors,
                        assigned=positions.selectors,
                        loc=selectors_loc,
                        code="hal.optical_routing.route.selector",
                        label="selector",
                    )
                violations += self.check_discrete_axis_positions(positions.selectors, loc=selectors_loc)
                for selector in positions.selectors:
                    selector_owners.setdefault(selector, {}).setdefault(dimension, route)

        for selector, owners in selector_owners.items():
            first_dimension = next(iter(owners))
            for dimension, route in list(owners.items())[1:]:
                violations.append(
                    Violation(
                        code="hal.optical_routing.selector_shared",
                        msg=(
                            f"Selector '{selector}' is also used by routing dimension '{first_dimension}'; "
                            "selectors may belong to only 1 dimension."
                        ),
                        loc=(*loc, "optical_routing", dimension, "routes", route, "selectors", selector),
                    )
                )
            if selector in self.filter_wheels:
                for dimension, route in owners.items():
                    violations.append(
                        Violation(
                            code="hal.optical_routing.selector_is_filter_wheel",
                            msg=f"Selector '{selector}' is already assigned as a filter wheel.",
                            loc=(*loc, "optical_routing", dimension, "routes", route, "selectors", selector),
                        )
                    )
        return violations


__all__ = [
    "DetectionPath",
    "DiscreteAxisPositions",
    "HALConfig",
    "IlluminationPath",
    "OpticalPath",
    "OpticalRouteDefinition",
    "OpticalRouting",
    "SelectRoutingDefinition",
    "SplitRoutingDefinition",
]

"""Static microscope hardware topology models and validation."""

import logging
from collections.abc import Mapping
from typing import Self

from pydantic import ConfigDict, Field, RootModel, field_validator, model_validator
from vxlib.schema import FrozenModel

from rigup import DeviceConfig, RigConfig

from .errors import Violation, ViolationLoc, assignment_violations

logger = logging.getLogger(__name__)


class StageAxes(FrozenModel):
    x: str
    y: str
    z: str


class OpticalAssembly(FrozenModel):
    aux_devices: list[str] = Field(default_factory=list)
    routing: set[str] = Field(default_factory=set)


class DetectionAssembly(OpticalAssembly):
    filter_wheels: list[str]
    magnification: float = Field(..., gt=0, description="Optical magnification of the detection path")
    rotation_deg: int = Field(0, description="Camera rotation relative to stage axes (multiple of 90)")

    @field_validator("rotation_deg")
    @classmethod
    def _validate_rotation(cls, v: int) -> int:
        if v % 90 != 0:
            raise ValueError(f"rotation_deg must be a multiple of 90, got {v}")
        return v

    @field_validator("filter_wheels")
    @classmethod
    def _validate_unique_filter_wheels(cls, value: list[str]) -> list[str]:
        if duplicates := sorted({uid for uid in value if value.count(uid) > 1}):
            raise ValueError(f"filter wheels must be unique (duplicates: {duplicates})")
        return value


class IlluminationAssembly(OpticalAssembly): ...


type DiscreteAxisPositions = dict[str, str]
type RouteByDimension = dict[str, str]
type RoutingSelectorOwners = dict[str, RouteByDimension]


class OpticalRouteDefinition(RootModel[DiscreteAxisPositions]):
    """One named optical route: discrete-axis UID to selected position label."""

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_has_selectors(self) -> Self:
        if not self.root:
            raise ValueError("Optical routes must define at least one selector")
        return self


class OpticalRouting(RootModel[dict[str, dict[str, OpticalRouteDefinition]]]):
    """Routing dimensions keyed directly to their named routes.

    Example:
        ```yaml
         excitation_side:
             left:
                 excitation_side_selector_1: left
                 excitation_side_selector_2: left
             right:
                 excitation_side_selector_1: right
                 excitation_side_selector_2: right
        ```
    """

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_dimensions_have_routes(self) -> Self:
        empty = [dimension for dimension, routes in self.root.items() if not routes]
        if empty:
            raise ValueError(f"Optical routing dimensions must define at least one route: {', '.join(empty)}")
        return self


class HardwareTopology(RigConfig, frozen=True):
    """The hardware blueprint: a rig (``devices`` + ``nodes``, inherited) plus the microscope wiring
    (stage axes, optical assemblies, and routing). Immutable — loaded once, never edited at runtime."""

    stage: StageAxes
    detection: dict[str, DetectionAssembly]
    illumination: dict[str, IlluminationAssembly]
    optical_routing: OpticalRouting = Field(default_factory=lambda: OpticalRouting({}))

    @property
    def device_uids(self) -> set[str]:
        node_devices = {did for node in self.nodes.values() for did in node.devices}
        return node_devices | set(self.devices.keys())

    @property
    def device_configs(self) -> dict[str, DeviceConfig]:
        configs = dict(self.devices)
        for node in self.nodes.values():
            configs.update(node.devices)
        return configs

    @property
    def filter_wheels(self) -> set[str]:
        fws: set[str] = set()
        for path in self.detection.values():
            fws.update(path.filter_wheels)
        return fws

    def check_discrete_axis_positions(self, positions: DiscreteAxisPositions, *, loc: ViolationLoc) -> list[Violation]:
        """Check device references and requested labels without importing device classes."""
        violations = []
        for device_uid, position in positions.items():
            device = self.device_configs.get(device_uid)
            if device is None:
                violations.append(
                    Violation(
                        code="discrete_axis.device_missing",
                        msg=f"Device '{device_uid}' is not configured.",
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
        """Return all statically knowable relationships that conflict within the HAL config."""
        return [
            *self._stage_violations(loc),
            *self._assembly_violations(loc),
            *self._optical_routing_violations(loc),
        ]

    def _stage_violations(self, loc: ViolationLoc) -> list[Violation]:
        devices = self.device_uids
        violations = []

        # Explicit mapping ensures type-safety and allows safe IDE refactoring
        stage_axes = {"x": self.stage.x, "y": self.stage.y, "z": self.stage.z}

        for axis_name, axis_device in stage_axes.items():
            if axis_device not in devices:
                violations.append(
                    Violation(
                        code="hal.stage.device_missing",
                        msg=f"Stage axis '{axis_name}' references missing device '{axis_device}'.",
                        loc=(*loc, "stage", axis_name),
                    )
                )

        return violations

    def _assembly_violations(self, loc: ViolationLoc) -> list[Violation]:
        devices = self.device_uids
        violations = []

        for assembly_id, assembly in self.detection.items():
            if assembly_id not in devices:
                violations.append(
                    Violation(
                        code="hal.detection.device_missing",
                        msg=f"Detection assembly '{assembly_id}' has no matching device.",
                        loc=(*loc, "detection", assembly_id),
                    )
                )
            for index, fw in enumerate(assembly.filter_wheels):
                if fw not in devices:
                    violations.append(
                        Violation(
                            code="hal.detection.filter_wheel_missing",
                            msg=f"Filter wheel '{fw}' is not configured.",
                            loc=(*loc, "detection", assembly_id, "filter_wheels", index),
                        )
                    )
            for index, aux in enumerate(assembly.aux_devices):
                if aux not in devices:
                    violations.append(
                        Violation(
                            code="hal.detection.aux_device_missing",
                            msg=f"Auxiliary device '{aux}' is not configured.",
                            loc=(*loc, "detection", assembly_id, "aux_devices", index),
                        )
                    )

        for assembly_id, assembly in self.illumination.items():
            if assembly_id not in devices:
                violations.append(
                    Violation(
                        code="hal.illumination.device_missing",
                        msg=f"Illumination assembly '{assembly_id}' has no matching device.",
                        loc=(*loc, "illumination", assembly_id),
                    )
                )
            for index, aux in enumerate(assembly.aux_devices):
                if aux not in devices:
                    violations.append(
                        Violation(
                            code="hal.illumination.aux_device_missing",
                            msg=f"Auxiliary device '{aux}' is not configured.",
                            loc=(*loc, "illumination", assembly_id, "aux_devices", index),
                        )
                    )

        return violations

    def _optical_routing_violations(self, loc: ViolationLoc) -> list[Violation]:
        assembly_violations, referenced_dimensions = self._assembly_routing_violations(loc)
        topology_violations, selector_owners = self._routing_topology_violations(loc, referenced_dimensions)
        return [
            *assembly_violations,
            *topology_violations,
            *self._selector_ownership_violations(loc, selector_owners),
        ]

    def _assembly_routing_violations(self, loc: ViolationLoc) -> tuple[list[Violation], set[str]]:
        violations = []
        referenced_dimensions: set[str] = set()
        assembly_groups = (("detection", self.detection), ("illumination", self.illumination))
        for assembly_type, assemblies in assembly_groups:
            for assembly_id, assembly in assemblies.items():
                for dimension in assembly.routing:
                    if dimension not in self.optical_routing.root:
                        violations.append(
                            Violation(
                                code="hal.optical_routing.participation.dimension_missing",
                                msg=f"Routing dimension '{dimension}' is not configured.",
                                loc=(*loc, assembly_type, assembly_id, "routing", dimension),
                            )
                        )
                        continue
                    referenced_dimensions.add(dimension)
        return violations, referenced_dimensions

    def _routing_topology_violations(
        self,
        loc: ViolationLoc,
        referenced_dimensions: set[str],
    ) -> tuple[list[Violation], RoutingSelectorOwners]:
        violations = []
        selector_owners: RoutingSelectorOwners = {}
        for dimension, routes in self.optical_routing.root.items():
            if dimension not in referenced_dimensions:
                violations.append(
                    Violation(
                        code="hal.optical_routing.dimension_unused",
                        msg=f"Routing dimension '{dimension}' is not used by any optical assembly.",
                        loc=(*loc, "optical_routing", dimension),
                    )
                )

            first_route, first_positions = next(iter(routes.items()))
            expected_selectors = first_positions.root.keys()
            for route, positions in routes.items():
                if route != first_route:
                    violations.extend(
                        assignment_violations(
                            expected=expected_selectors,
                            assigned=positions.root,
                            loc=(*loc, "optical_routing", dimension, route),
                            code="hal.optical_routing.route.selector",
                            label="selector",
                        )
                    )
                violations.extend(
                    self.check_discrete_axis_positions(
                        positions.root,
                        loc=(*loc, "optical_routing", dimension, route),
                    )
                )
                for selector_uid in positions.root:
                    selector_owners.setdefault(selector_uid, {}).setdefault(dimension, route)
        return violations, selector_owners

    def _selector_ownership_violations(
        self,
        loc: ViolationLoc,
        selector_owners: RoutingSelectorOwners,
    ) -> list[Violation]:
        violations = []
        for selector_uid, owners in selector_owners.items():
            first_dimension = next(iter(owners))
            for dimension, route in list(owners.items())[1:]:
                violations.append(
                    Violation(
                        code="hal.optical_routing.selector_shared",
                        msg=(
                            f"Selector '{selector_uid}' is also used by routing dimension "
                            f"'{first_dimension}'; selectors may belong to only one dimension."
                        ),
                        loc=(*loc, "optical_routing", dimension, route, selector_uid),
                    )
                )
            if selector_uid in self.filter_wheels:
                for dimension, route in owners.items():
                    violations.append(
                        Violation(
                            code="hal.optical_routing.selector_is_filter_wheel",
                            msg=f"Selector '{selector_uid}' is already assigned as a filter wheel.",
                            loc=(*loc, "optical_routing", dimension, route, selector_uid),
                        )
                    )
        return violations

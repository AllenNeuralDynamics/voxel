"""The ``hal`` part of an instrument file."""

from collections.abc import Mapping

from pydantic import Field
from rigup.config import DeviceUid, RigConfig
from vxlib.schema import FrozenModel

from vxl.config.basics import SPECIMEN_AXES, PartName, SpecimenAxis, Violation, not_configured, under

from .light import SAMPLE, LightGraph, PositionValue, targets
from .wiring import Wiring


class PartConfig(FrozenModel):
    """A part with no driver, such as a galvo, a tunable lens or an objective."""

    label: str | None = None


class Stage(FrozenModel):
    """The device that drives each specimen axis."""

    x: DeviceUid
    y: DeviceUid
    z: DeviceUid

    def device(self, axis: SpecimenAxis) -> DeviceUid:
        return getattr(self, axis)


class HALConfig(RigConfig, frozen=True):
    """The rig's devices and nodes, plus parts, wiring, the light graph and the stage."""

    parts: dict[PartName, PartConfig] = Field(default_factory=dict)
    wiring: Wiring = Field(default_factory=lambda: Wiring({}))
    light: LightGraph
    stage: Stage

    @property
    def discrete_axis_labels(self) -> dict[str, list[str]]:
        """The named positions of each discrete axis, from its ``init.slots``."""
        found: dict[str, list[str]] = {}
        for uid, config in self.device_configs.items():
            slots = config.init.get("slots")
            if isinstance(slots, Mapping):
                found[uid] = [
                    slot if isinstance(slot, str) else slot["label"]
                    for slot in slots.values()
                    if isinstance(slot, str) or (isinstance(slot, Mapping) and isinstance(slot.get("label"), str))
                ]
        return found

    def position_problem(self, device: DeviceUid, value: PositionValue) -> str | None:
        """Why ``value`` is not a position of ``device``, or ``None`` when it is."""
        labels = self.discrete_axis_labels.get(device)
        if labels is not None:
            return None if value in labels else f"'{value}' is not a position of '{device}' {labels}."
        if isinstance(value, str):
            return f"'{device}' declares no slots, so its position is a number in µm, not '{value}'."
        return None

    def violations(self) -> list[Violation]:
        """Return the problems that ``hal`` alone shows."""
        devices, parts = self.device_uids, self.parts
        return [
            *self._name_violations(),
            *under(("wiring",), self.wiring.violations(devices=devices, parts=parts)),
            *under(("light",), self.light.violations(devices=devices, parts=parts, labels=self.discrete_axis_labels)),
        ]

    def _name_violations(self) -> list[Violation]:
        violations = [
            not_configured("Device", device, code="hal.stage.device_missing", loc=("stage", axis))
            for axis in SPECIMEN_AXES
            if (device := self.stage.device(axis)) not in self.device_uids
        ]
        if SAMPLE in self.parts or SAMPLE in self.device_uids:
            violations.append(
                Violation(
                    code="hal.reserved_name",
                    msg="'sample' names the node where the 2 sides of the light graph meet, so no device or part "
                    "takes it.",
                    loc=("parts" if SAMPLE in self.parts else "devices", SAMPLE),
                )
            )
        violations += [
            Violation(
                code="hal.parts.device_name",
                msg=f"'{part}' is a device, so it is not also a part.",
                loc=("parts", part),
            )
            for part in self.parts
            if part in self.device_uids
        ]
        used = {pin.device for group in self.wiring.root.values() for wire in group.values() for pin in wire.to}
        used.update(self.light.root)
        used.update(target for entry in self.light.root.values() for target in targets(entry))
        violations += [
            Violation(
                code="hal.parts.unused",
                msg=f"Part '{part}' is not used by any wire or light node.",
                loc=("parts", part),
            )
            for part in self.parts
            if part not in used
        ]
        return violations


__all__ = ["HALConfig", "PartConfig", "Stage"]

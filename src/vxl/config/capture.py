"""The CaptureEngine's settings block, ``hal.capture.<modality>``: the frame rhythm and the scan axes."""

from importlib.metadata import entry_points
from typing import Annotated, Self

from pydantic import Discriminator, Tag, model_validator
from rigup.config import DeviceUid
from vxlib.schema import FrozenModel, NoSettings, check_identifier, identifier, repeated, single_key_tag
from vxlib.units import Portion

from .specimen import SPECIMEN_AXES, SpecimenAxis

Modality = Annotated[str, identifier("Modality")]
"""The name of an installed CaptureEngine, such as ``light_sheet``."""

CAPTURE_SETTINGS_GROUP = "vxl.capture_settings"
"""Entry point group: each modality name points to its CaptureEngine's settings model."""


class TimeSync(FrozenModel):
    """A clock sets the frame rhythm: a signal generator, or a camera's exposure output."""

    time: DeviceUid


class PositionSync(FrozenModel):
    """A sweeping axis sets the frame rhythm with 1 pulse every spacing."""

    position: DeviceUid


class SoftwareSync(FrozenModel):
    """The program moves, waits, then starts each frame."""

    software: NoSettings


class StepSettings(FrozenModel):
    axis: SpecimenAxis


class SweepSettings(FrozenModel):
    axis: SpecimenAxis
    margin: Portion
    """How far below the highest speed the axis runs, so a slightly fast stage never skips a frame."""


class Step(FrozenModel):
    """Move, stop, then capture: 1 frame at each position."""

    step: StepSettings

    @property
    def axis(self) -> SpecimenAxis:
        return self.step.axis


class Sweep(FrozenModel):
    """Keep moving while capturing: 1 frame or line for each pulse or clock tick."""

    sweep: SweepSettings

    @property
    def axis(self) -> SpecimenAxis:
        return self.sweep.axis


type SyncChoice = Annotated[
    Annotated[TimeSync, Tag("time")]
    | Annotated[PositionSync, Tag("position")]
    | Annotated[SoftwareSync, Tag("software")],
    Discriminator(
        single_key_tag,
        custom_error_type="one_key",
        custom_error_message="write exactly 1 of: 'time', 'position', 'software'",
    ),
]
type Movement = Annotated[
    Annotated[Step, Tag("step")] | Annotated[Sweep, Tag("sweep")],
    Discriminator(
        single_key_tag, custom_error_type="one_key", custom_error_message="write exactly 1 of: 'step', 'sweep'"
    ),
]


class CaptureSettings(FrozenModel):
    """The settings every CaptureEngine has. An engine's own model adds the fields only it has."""

    sync: SyncChoice
    scan: list[Movement]
    """The data axes a capture adds after the frame, innermost first. Every other stage axis is tiled."""

    @model_validator(mode="after")
    def _check_scan(self) -> Self:
        if duplicates := repeated(movement.axis for movement in self.scan):
            raise ValueError(f"each axis appears at most once in scan (repeated: {duplicates})")
        steps = [index for index, movement in enumerate(self.scan) if isinstance(movement, Step)]
        sweeps = [index for index, movement in enumerate(self.scan) if isinstance(movement, Sweep)]
        if steps and sweeps and min(steps) < max(sweeps):
            raise ValueError("a step cannot happen during a running sweep, so every sweep comes before every step")
        return self

    @property
    def sender(self) -> str | None:
        """The device that sets the frame rhythm, or ``None`` with software sync."""
        match self.sync:
            case TimeSync(time=device) | PositionSync(position=device):
                return device
            case SoftwareSync():
                return None

    @property
    def scan_axes(self) -> list[SpecimenAxis]:
        """The axes a capture moves, innermost first."""
        return [movement.axis for movement in self.scan]

    @property
    def tiled_axes(self) -> list[SpecimenAxis]:
        """The stage axes a capture does not move, so the outer loops place several captures along them."""
        return [axis for axis in SPECIMEN_AXES if axis not in self.scan_axes]

    def spacing_axes(self) -> list[SpecimenAxis]:
        """The scan axes that need a spacing in each profile. An engine overrides this when optics fix one."""
        return self.scan_axes


def installed_capture_settings() -> dict[Modality, type[CaptureSettings]]:
    """Return the settings model of each installed CaptureEngine, by modality."""
    models: dict[Modality, type[CaptureSettings]] = {}
    for entry in entry_points(group=CAPTURE_SETTINGS_GROUP):
        check_identifier(entry.name, "Modality")
        model = entry.load()
        if not (isinstance(model, type) and issubclass(model, CaptureSettings)):
            raise TypeError(f"entry point '{entry.name}' in {CAPTURE_SETTINGS_GROUP} is not a CaptureSettings model")
        models[entry.name] = model
    return models


__all__ = [
    "CAPTURE_SETTINGS_GROUP",
    "CaptureSettings",
    "Modality",
    "Movement",
    "PositionSync",
    "SoftwareSync",
    "Step",
    "StepSettings",
    "Sweep",
    "SweepSettings",
    "SyncChoice",
    "TimeSync",
    "installed_capture_settings",
]

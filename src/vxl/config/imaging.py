"""Channels and profiles: what each capture images and with which settings."""

from typing import Annotated, Any

from pydantic import Field, ValidationInfo, field_validator
from rigup.config import DeviceUid
from rigup.device.schema import CommandRequest
from vxlib.schema import FrozenModel, repeated

from vxl._utils.color import Color

from .hal import DiscreteAxisPositions, HALConfig
from .identifiers import ChannelId, ProfileId
from .specimen import SpecimenAxis
from .sync import GeneratorSync, sync_violations
from .violations import Violation, ViolationLoc, assignment_violations, not_configured

PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class ChannelConfig(FrozenModel):
    """1 detection path with 1 illumination path and its filter positions."""

    detection: DeviceUid
    illumination: DeviceUid
    filters: DiscreteAxisPositions = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None
    emission: float | None = None
    """Peak emission wavelength in nm."""

    @field_validator("emission")
    @classmethod
    def _check_emission(cls, value: float | None) -> float | None:
        if value is not None and not 200 <= value <= 2000:
            raise ValueError(f"emission wavelength out of reasonable range: {value} nm")
        return value

    @property
    def colormap(self) -> str:
        """Colormap from the emission wavelength; ``'white'`` outside the visible range or when unknown."""
        if not self.emission:
            return "white"
        color = str(Color.from_wavelength(self.emission))
        return color if color != "#000000" else "white"


class AreaFov(FrozenModel):
    """The sensor region of an area camera, in pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class LineFov(FrozenModel):
    """The pixels used along the line of a line camera."""

    x: int = Field(ge=0)
    w: int = Field(gt=0)


type Fov = AreaFov | LineFov


class ProfileConfig(FrozenModel):
    """A named set of channels with the device values, field of view, spacing and signals they use."""

    channels: list[ChannelId] = Field(min_length=1)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    fov: dict[DeviceUid, Fov]
    spacing: dict[SpecimenAxis, float] = Field(default_factory=dict)
    """µm between frames along each moving axis that needs it."""
    sync: dict[DeviceUid, GeneratorSync] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None

    @field_validator("spacing")
    @classmethod
    def _positive_spacing(cls, value: dict[str, float]) -> dict[str, float]:
        if bad := sorted(axis for axis, spacing in value.items() if not spacing > 0):
            raise ValueError(f"spacing must be greater than 0 (axes: {bad})")
        return value


class ImagingConfig(FrozenModel):
    channels: dict[ChannelId, ChannelConfig]
    profiles: dict[ProfileId, ProfileConfig]

    @field_validator("channels", "profiles")
    @classmethod
    def _at_least_one(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        if not value:
            raise ValueError(f"at least 1 {(info.field_name or 'entry').rstrip('s')} must be present")
        return value

    def active_cameras(self, profile_id: str) -> set[str]:
        """The detection paths of the profile's known channels."""
        profile = self.profiles[profile_id]
        return {self.channels[ch].detection for ch in profile.channels if ch in self.channels}

    def settable_devices(self, profile_id: str, hal: HALConfig) -> set[str]:
        """The devices a profile may give values to: its channels' devices and aux devices, and its generators."""
        ids: set[str] = set(self.profiles[profile_id].sync)
        for ch_id in self.profiles[profile_id].channels:
            if (channel := self.channels.get(ch_id)) is None:
                continue
            ids.update({channel.detection, channel.illumination, *channel.filters})
            if (detection := hal.detection.get(channel.detection)) is not None:
                ids.update(detection.aux_devices)
            if (illumination := hal.illumination.get(channel.illumination)) is not None:
                ids.update(illumination.aux_devices)
        return ids - hal.filter_wheels

    def logical_violations(self, *, loc: ViolationLoc) -> list[Violation]:
        """Return relationships inside the imaging config that cannot be met."""
        violations = []
        for profile_id, profile in self.profiles.items():
            profile_loc = (*loc, "profiles", profile_id)
            if duplicates := repeated(profile.channels):
                violations.append(
                    Violation(
                        code="imaging.profile.channels_duplicate",
                        msg=f"Channels must be unique (duplicates: {duplicates}).",
                        loc=(*profile_loc, "channels"),
                    )
                )
            for index, ch_id in enumerate(profile.channels):
                if ch_id not in self.channels:
                    violations.append(
                        not_configured(
                            "Channel",
                            ch_id,
                            code="imaging.profile.channel_missing",
                            loc=(*profile_loc, "channels", index),
                        )
                    )
            known = list(dict.fromkeys(ch for ch in profile.channels if ch in self.channels))
            detection_channel: dict[str, str] = {}
            filter_positions: dict[str, dict[str, list[str]]] = {}
            for ch_id in known:
                channel = self.channels[ch_id]
                if channel.detection in detection_channel:
                    violations.append(
                        Violation(
                            code="imaging.profile.detection_conflict",
                            msg=(
                                f"Channels '{detection_channel[channel.detection]}' and '{ch_id}' both use "
                                f"detection path '{channel.detection}'."
                            ),
                            loc=(*profile_loc, "channels"),
                        )
                    )
                else:
                    detection_channel[channel.detection] = ch_id
                for wheel, position in channel.filters.items():
                    filter_positions.setdefault(wheel, {}).setdefault(position, []).append(ch_id)
            for wheel, positions in filter_positions.items():
                if len(positions) > 1:
                    details = ", ".join(f"'{position}' by {chs}" for position, chs in positions.items())
                    violations.append(
                        Violation(
                            code="imaging.profile.filter_conflict",
                            msg=f"Filter wheel '{wheel}' is given conflicting positions: {details}.",
                            loc=(*profile_loc, "channels"),
                        )
                    )
            if known:
                violations += assignment_violations(
                    expected=self.active_cameras(profile_id),
                    assigned=profile.fov,
                    loc=(*profile_loc, "fov"),
                    code="imaging.profile.fov",
                    label="fov",
                )
        return violations

    def hal_violations(self, hal: HALConfig, *, loc: ViolationLoc) -> list[Violation]:
        """Return relationships between the imaging config and ``hal`` that cannot resolve."""
        violations = []
        for ch_id, channel in self.channels.items():
            ch_loc = (*loc, "channels", ch_id)
            detection = hal.detection.get(channel.detection)
            if detection is None:
                violations.append(
                    not_configured(
                        "Detection path",
                        channel.detection,
                        code="imaging.channel.detection_missing",
                        loc=(*ch_loc, "detection"),
                    )
                )
            else:
                violations += assignment_violations(
                    expected=detection.filter_wheels,
                    assigned=channel.filters,
                    loc=(*ch_loc, "filters"),
                    code="imaging.channel.filter",
                    label="filter-wheel",
                )
                expected = set(detection.filter_wheels)
                violations += hal.check_discrete_axis_positions(
                    {uid: position for uid, position in channel.filters.items() if uid in expected},
                    loc=(*ch_loc, "filters"),
                )
            if channel.illumination not in hal.illumination:
                violations.append(
                    not_configured(
                        "Illumination path",
                        channel.illumination,
                        code="imaging.channel.illumination_missing",
                        loc=(*ch_loc, "illumination"),
                    )
                )

        spacing_axes = hal.capture_settings.spacing_axes()
        for profile_id, profile in self.profiles.items():
            profile_loc = (*loc, "profiles", profile_id)
            violations += assignment_violations(
                expected=spacing_axes,
                assigned=profile.spacing,
                loc=(*profile_loc, "spacing"),
                code="imaging.profile.spacing",
                label="spacing",
            )
            for camera, fov in profile.fov.items():
                if (path := hal.detection.get(camera)) is None:
                    continue
                if (path.geometry.height is None) != isinstance(fov, LineFov):
                    needs = "a line fov {x, w}" if path.geometry.height is None else "an area fov {x, y, w, h}"
                    violations.append(
                        Violation(
                            code="imaging.profile.fov_shape",
                            msg=f"Camera '{camera}' needs {needs}, as its detection geometry says.",
                            loc=(*profile_loc, "fov", camera),
                        )
                    )
            settable = self.settable_devices(profile_id, hal)
            for device_id in profile.props:
                if device_id not in settable:
                    violations.append(
                        Violation(
                            code="imaging.profile.props_inactive",
                            msg=f"Device '{device_id}' is not active in this profile.",
                            loc=(*profile_loc, "props", device_id),
                        )
                    )
            for device_id in profile.setup:
                if device_id not in settable | hal.filter_wheels:
                    violations.append(
                        Violation(
                            code="imaging.profile.setup_inactive",
                            msg=f"Device '{device_id}' is not active in this profile.",
                            loc=(*profile_loc, "setup", device_id),
                        )
                    )
            for generator, sync in profile.sync.items():
                violations += sync_violations(hal, generator, sync, loc=(*profile_loc, "sync", generator))
        return violations


__all__ = [
    "AreaFov",
    "ChannelConfig",
    "Fov",
    "ImagingConfig",
    "LineFov",
    "ProfileConfig",
    "PropertyName",
]

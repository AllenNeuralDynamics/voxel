"""Channels and profiles: what each capture images and with which settings."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field, ValidationInfo, field_validator
from rigup.config import DeviceUid
from rigup.device.schema import CommandRequest
from vxlib.schema import FrozenModel, repeated

from vxl.config.basics import ChannelId, ProfileId, Violation, assignment_violations, not_configured, under
from vxl.config.hal import HALConfig
from vxl.config.light import LightPath, PositionValue
from vxl.roi import AreaROI, LineROI

if TYPE_CHECKING:
    from vxl.instrument_next.engine import Engine

PropertyName = Annotated[str, Field(min_length=1)]
"""The name of a property that a device class declares, such as ``exposure_time_ms``."""


class ChannelConfig(FrozenModel):
    """1 light source and 1 camera, with the position of each ``set_by: channel`` axis on their paths. ``emission`` is
    the peak emission wavelength in nm."""

    illumination: DeviceUid
    detection: DeviceUid
    positions: dict[DeviceUid, PositionValue] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None
    emission: float | None = None

    @field_validator("emission")
    @classmethod
    def _check_emission(cls, value: float | None) -> float | None:
        if value is not None and not 200 <= value <= 2000:
            raise ValueError(f"emission wavelength out of reasonable range: {value} nm")
        return value


class ProfileConfig(FrozenModel):
    """A named set of channels and the settings they use. ``fov`` is the sensor region each camera reads out; ``engine``
    belongs to the engine, which reads it, and stays as written."""

    channels: list[ChannelId] = Field(min_length=1)
    props: dict[DeviceUid, dict[PropertyName, Any]] = Field(default_factory=dict)
    setup: dict[DeviceUid, list[CommandRequest]] = Field(default_factory=dict)
    fov: dict[DeviceUid, AreaROI | LineROI]
    positions: dict[DeviceUid, PositionValue] = Field(default_factory=dict)
    engine: dict[str, Any] = Field(default_factory=dict)
    desc: str = ""
    label: str | None = None


@dataclass(frozen=True)
class LightSetting:
    """The light paths of 1 capture: the position of every axis that a rule sets, and each camera's magnification."""

    positions: dict[DeviceUid, PositionValue]
    magnification: dict[DeviceUid, float]


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
        """The cameras of the profile's known channels."""
        profile = self.profiles[profile_id]
        return {self.channels[ch].detection for ch in profile.channels if ch in self.channels}

    def channel_paths(self, channel_id: str, hal: HALConfig) -> list[LightPath]:
        """Every way the light of 1 channel goes from its source to its detector."""
        channel = self.channels[channel_id]
        return hal.light.paths(channel.illumination, channel.detection)

    def path_nodes(self, profile_id: str, hal: HALConfig) -> set[str]:
        """Every node on the light paths of the profile's known channels."""
        known = [ch for ch in self.profiles[profile_id].channels if ch in self.channels]
        return {node for ch in known for path in self.channel_paths(ch, hal) for node in path.nodes}

    def settable_devices(self, profile_id: str, hal: HALConfig, engine: "Engine[Any]") -> set[str]:
        """The devices a profile may set in ``props``: those on its light paths that no rule sets and the engine does
        not own."""
        nodes = self.path_nodes(profile_id, hal)
        free = {node for node in nodes if node in hal.device_uids and hal.light.rules().get(node) is None}
        return free - engine.owned_devices()

    def light_setting(self, profile_id: str, hal: HALConfig, picks: Mapping[str, PositionValue]) -> LightSetting:
        """The light paths of 1 capture of a profile. ``picks`` gives the positions of the ``stage`` rules. Raise
        ``ValueError`` when a channel has no lit path or 2 magnifications, or when 2 channels need different
        positions."""
        profile = self.profiles[profile_id]
        positions: dict[str, PositionValue] = {}
        setters: dict[str, str] = {}
        magnification: dict[str, float] = {}
        for ch_id in profile.channels:
            channel = self.channels[ch_id]
            chosen = {**picks, **profile.positions, **channel.positions}
            paths = self.channel_paths(ch_id, hal)
            lit = [path for path in paths if all(chosen.get(d, p) == p for d, p in path.positions.items())]
            if not lit:
                on_paths = {node for path in paths for node in path.nodes}
                given = ", ".join(f"{device} at {value}" for device, value in chosen.items() if device in on_paths)
                raise ValueError(f"Channel '{ch_id}' has no lit light path with {given or 'no positions'}.")
            needed: dict[str, PositionValue] = {
                device: position for path in lit for device, position in path.positions.items()
            }
            lit_nodes = {node for path in lit for node in path.nodes}
            needed.update({node: value for node, value in chosen.items() if node in lit_nodes})
            for node, value in needed.items():
                if hal.light.rules().get(node) is None:
                    continue
                if node in positions and positions[node] != value:
                    raise ValueError(
                        f"Channels '{setters[node]}' and '{ch_id}' need '{node}' at different positions: "
                        f"{positions[node]} and {value}."
                    )
                positions[node], setters[node] = value, ch_id
            found = {path.magnification for path in lit}
            value = found.pop() if len(found) == 1 else None
            if value is None:
                raise ValueError(f"The lit light paths to '{channel.detection}' do not give 1 magnification.")
            magnification[channel.detection] = value
        return LightSetting(positions=positions, magnification=magnification)

    def violations(self, hal: HALConfig, engine: "Engine[Any]") -> list[Violation]:
        """Return the problems of the channels and profiles, alone and against ``hal`` and ``engine``."""
        violations: list[Violation] = []
        valid: set[str] = set()
        for channel_id, channel in self.channels.items():
            found = self._channel_violations(channel_id, channel, hal)
            if not found:
                valid.add(channel_id)
            violations += under(("channels", channel_id), found)
        for profile_id, profile in self.profiles.items():
            found = [
                *self._profile_channels_violations(profile_id, profile),
                *self._profile_violations(profile_id, profile, hal, engine, valid),
            ]
            violations += under(("profiles", profile_id), found)
        return violations

    def _channel_violations(self, channel_id: str, channel: ChannelConfig, hal: HALConfig) -> list[Violation]:
        violations = []
        if channel.illumination not in hal.light.sources():
            violations.append(
                Violation(
                    code="imaging.channel.illumination_missing",
                    msg=f"'{channel.illumination}' is not a light source: no node of hal.light sends light to it.",
                    loc=("illumination",),
                )
            )
        if channel.detection not in hal.light.detectors():
            violations.append(
                Violation(
                    code="imaging.channel.detection_missing",
                    msg=f"'{channel.detection}' is not a detector of hal.light: a detector's node has no 'to'.",
                    loc=("detection",),
                )
            )
        if violations:
            return violations

        paths = self.channel_paths(channel_id, hal)
        if not paths:
            msg = f"No light path goes from '{channel.illumination}' through the sample to '{channel.detection}'."
            return [Violation(code="imaging.channel.no_path", msg=msg)]

        nodes = {node for path in paths for node in path.nodes}
        expected = [node for node in nodes if hal.light.rules().get(node) == "channel"]
        violations += assignment_violations(
            expected=expected,
            assigned=channel.positions,
            loc=("positions",),
            code="imaging.channel.position",
            label="channel position",
        )
        violations += under(
            ("positions",),
            self._position_violations(channel.positions, expected, hal, code="imaging.channel.position_invalid"),
        )
        return violations

    def _profile_channels_violations(self, profile_id: str, profile: ProfileConfig) -> list[Violation]:
        """The problems of a profile's channels: each known and listed once, 1 camera each, positions that agree, and a
        ``fov`` for each camera."""
        violations = []
        if duplicates := repeated(profile.channels):
            violations.append(
                Violation(
                    code="imaging.profile.channels_duplicate",
                    msg=f"Channels must be unique (duplicates: {duplicates}).",
                    loc=("channels",),
                )
            )
        violations += [
            not_configured("Channel", ch_id, code="imaging.profile.channel_missing", loc=("channels", index))
            for index, ch_id in enumerate(profile.channels)
            if ch_id not in self.channels
        ]
        known = list(dict.fromkeys(ch for ch in profile.channels if ch in self.channels))
        camera_channel: dict[str, str] = {}
        given: dict[str, dict[PositionValue, list[str]]] = {}
        for ch_id in known:
            channel = self.channels[ch_id]
            if channel.detection in camera_channel:
                violations.append(
                    Violation(
                        code="imaging.profile.detection_conflict",
                        msg=(
                            f"Channels '{camera_channel[channel.detection]}' and '{ch_id}' both use "
                            f"camera '{channel.detection}'."
                        ),
                        loc=("channels",),
                    )
                )
            else:
                camera_channel[channel.detection] = ch_id
            for device, value in channel.positions.items():
                given.setdefault(device, {}).setdefault(value, []).append(ch_id)
        for device, values in given.items():
            if len(values) > 1:
                details = ", ".join(f"{value} by {chs}" for value, chs in values.items())
                violations.append(
                    Violation(
                        code="imaging.profile.position_conflict",
                        msg=f"The channels give '{device}' different positions: {details}.",
                        loc=("channels",),
                    )
                )
        if known:
            violations += assignment_violations(
                expected=self.active_cameras(profile_id),
                assigned=profile.fov,
                loc=("fov",),
                code="imaging.profile.fov",
                label="fov",
            )
        return violations

    def _profile_violations(
        self,
        profile_id: str,
        profile: ProfileConfig,
        hal: HALConfig,
        engine: "Engine[Any]",
        valid: set[str],
    ) -> list[Violation]:
        violations = []
        channels = [ch for ch in dict.fromkeys(profile.channels) if ch in valid]
        nodes = {node for ch in channels for path in self.channel_paths(ch, hal) for node in path.nodes}
        if channels and len(channels) == len(set(profile.channels)):
            expected = [node for node in nodes if hal.light.rules().get(node) == "profile"]
            violations += assignment_violations(
                expected=expected,
                assigned=profile.positions,
                loc=("positions",),
                code="imaging.profile.position",
                label="profile position",
            )
            violations += under(
                ("positions",),
                self._position_violations(profile.positions, expected, hal, code="imaging.profile.position_invalid"),
            )

        cameras = hal.light.detectors()
        for camera, fov in profile.fov.items():
            if (node := cameras.get(camera)) is None:
                continue
            if (node.height is None) != isinstance(fov, LineROI):
                needs = "a line fov {x, w}" if node.height is None else "an area fov {x, y, w, h}"
                violations.append(
                    Violation(
                        code="imaging.profile.fov_shape",
                        msg=f"Camera '{camera}' needs {needs}, as its light node says.",
                        loc=("fov", camera),
                    )
                )

        settable = self.settable_devices(profile_id, hal, engine)
        owned = engine.owned_devices()
        for device_id in profile.props:
            if device_id in settable:
                continue
            if device_id in owned:
                msg = f"The engine names '{device_id}', so it sets it."
            elif device_id not in nodes:
                msg = f"'{device_id}' is not on the light paths of this profile's channels."
            elif (rule := hal.light.rules().get(device_id)) is not None:
                msg = f"'{device_id}' has set_by: {rule if isinstance(rule, str) else rule.kind}, so its rule sets it."
            else:
                msg = f"'{device_id}' is a part, so it has no settings."
            violations.append(Violation(code="imaging.profile.props_inactive", msg=msg, loc=("props", device_id)))
        for device_id in profile.setup:
            if device_id not in nodes or device_id not in hal.device_uids or device_id in owned:
                violations.append(
                    Violation(
                        code="imaging.profile.setup_inactive",
                        msg=f"'{device_id}' is not a device on this profile's light paths that the engine leaves free.",
                        loc=("setup", device_id),
                    )
                )
        violations += under(("engine",), engine.profile_violations(profile))
        return violations

    @staticmethod
    def _position_violations(
        positions: Mapping[str, PositionValue], expected: list[str], hal: HALConfig, *, code: str
    ) -> list[Violation]:
        return [
            Violation(code=code, msg=problem, loc=(device,))
            for device, value in positions.items()
            if device in expected and (problem := hal.position_problem(device, value)) is not None
        ]


__all__ = [
    "ChannelConfig",
    "ImagingConfig",
    "LightSetting",
    "ProfileConfig",
    "PropertyName",
]

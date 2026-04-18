"""Microscope — replaces VoxelRig with composition over rigup.Rig.

Typed device access via inherited handles (CameraHandle, AnalogOutputHandle,
ContinuousAxisHandle). Stage grouping, device validation, and profiles management
match VoxelRig's public API so downstream code (controllers, web services)
needs no changes.
"""

import logging
from dataclasses import dataclass

from rigup import DeviceHandle, Rig
from vxl.analog_out import AnalogOutputHandle
from vxl.config import MicroscopeConfig

from .axes import ContinuousAxisHandle
from .camera import CameraHandle
from .profiles import Profiles

logger = logging.getLogger(__name__)

HANDLE_MAP: dict[str, type[DeviceHandle]] = {
    "camera": CameraHandle,
    "analog_output": AnalogOutputHandle,
    "continuous_axis": ContinuousAxisHandle,
}


@dataclass(frozen=True)
class Stage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.z


class Microscope:
    """Light sheet microscope built on :class:`Rig`.

    Public API matches the legacy VoxelRig surface: ``cameras``, ``lasers``,
    ``analog_outs``, ``stage``, ``profiles``, etc.
    """

    def __init__(self, config: MicroscopeConfig) -> None:
        self._config = config
        self._rig = Rig(config.rig)

        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DeviceHandle] = {}
        self.fws: dict[str, DeviceHandle] = {}
        self.analog_outs: dict[str, AnalogOutputHandle] = {}
        self.stage: Stage
        self.profiles = Profiles(self)

    @property
    def rig(self) -> Rig:
        return self._rig

    @property
    def config(self) -> MicroscopeConfig:
        return self._config

    @property
    def devices(self) -> dict[str, DeviceHandle]:
        return self.rig.devices

    async def open(self) -> None:
        await self._rig.open()
        await _categorize_handles(self)
        _validate_devices(self)
        self.stage = _build_stage(self)
        await self.profiles.open()

    async def close(self) -> None:
        await self.profiles.close()
        self.cameras.clear()
        self.lasers.clear()
        self.aotfs.clear()
        self.continuous_axes.clear()
        self.discrete_axes.clear()
        self.fws.clear()
        self.analog_outs.clear()
        await self._rig.close()


async def _categorize_handles(scope: Microscope) -> None:
    for uid, handle in scope.rig.devices.items():
        device_type = (await handle.interface()).type
        match device_type:
            case "camera":
                scope.cameras[uid] = CameraHandle.wrap(handle)
            case "analog_output":
                scope.analog_outs[uid] = AnalogOutputHandle.wrap(handle)
            case "laser":
                scope.lasers[uid] = handle
            case "aotf":
                scope.aotfs[uid] = handle
            case "continuous_axis":
                scope.continuous_axes[uid] = ContinuousAxisHandle.wrap(handle)
            case "discrete_axis":
                scope.discrete_axes[uid] = handle

    for fw_id in scope.config.filter_wheels:
        if fw_id in scope.rig.devices:
            scope.fws[fw_id] = scope.rig.devices[fw_id]


def _validate_devices(scope: Microscope) -> None:
    """Cross-check categorized handles against the microscope config.

    Delegates individual concerns to helper functions to keep this composition shallow.
    Raises ``ValueError`` with one bullet per collected problem on the first failure.
    """
    errors: list[str] = []
    errors.extend(_validate_camera_paths(scope))
    errors.extend(_validate_laser_paths(scope))
    errors.extend(_validate_profile_ao_refs(scope))
    errors.extend(_validate_stage_axes(scope))
    errors.extend(_validate_filter_wheels(scope))
    errors.extend(_validate_aux_not_reserved(scope))
    if errors:
        raise ValueError("Microscope device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


def _validate_camera_paths(scope: Microscope) -> list[str]:
    """Camera uids and detection-path uids must mutually cover each other."""
    errors: list[str] = []
    camera_ids = set(scope.cameras.keys())
    detection_ids = set(scope.config.detection.keys())
    if missing := camera_ids - detection_ids:
        errors.append(f"Cameras without detection paths: {missing}")
    if invalid := detection_ids - camera_ids:
        errors.append(f"Detection paths referencing non-camera devices: {invalid}")
    return errors


def _validate_laser_paths(scope: Microscope) -> list[str]:
    """Laser uids and illumination-path uids must mutually cover each other."""
    errors: list[str] = []
    laser_ids = set(scope.lasers.keys())
    illumination_ids = set(scope.config.illumination.keys())
    if missing := laser_ids - illumination_ids:
        errors.append(f"Lasers without illumination paths: {missing}")
    if invalid := illumination_ids - laser_ids:
        errors.append(f"Illumination paths referencing non-laser devices: {invalid}")
    return errors


def _validate_profile_ao_refs(scope: Microscope) -> list[str]:
    """Every AO device referenced by any profile must be provisioned on the rig."""
    referenced = {ao_uid for profile in scope.config.profiles.values() for ao_uid in profile.sync}
    missing = referenced - set(scope.analog_outs.keys())
    if missing:
        return [f"AO devices referenced by profiles not provisioned: {sorted(missing)}"]
    return []


def _validate_stage_axes(scope: Microscope) -> list[str]:
    """Stage X/Y/Z must resolve to continuous-axis devices."""
    stage_cfg = scope.config.stage
    stage_axis_ids = {stage_cfg.x, stage_cfg.y, stage_cfg.z}
    if invalid := stage_axis_ids - set(scope.continuous_axes.keys()):
        return [f"Stage axes are not continuous_axis devices: {invalid}"]
    return []


def _validate_filter_wheels(scope: Microscope) -> list[str]:
    """Declared filter wheels must be discrete-axis devices."""
    filter_wheel_ids = set(scope.config.filter_wheels)
    if invalid := filter_wheel_ids - set(scope.discrete_axes.keys()):
        return [f"Filter wheels are not discrete_axis devices: {invalid}"]
    return []


def _validate_aux_not_reserved(scope: Microscope) -> list[str]:
    """Aux devices listed on detection/illumination paths must not collide with reserved slots."""
    camera_ids = set(scope.cameras.keys())
    laser_ids = set(scope.lasers.keys())
    filter_wheel_ids = set(scope.config.filter_wheels)
    stage_cfg = scope.config.stage
    stage_axis_ids = {stage_cfg.x, stage_cfg.y, stage_cfg.z}
    reserved = camera_ids | laser_ids | filter_wheel_ids | stage_axis_ids | set(scope.analog_outs.keys())

    errors: list[str] = []
    for path_id, path in scope.config.detection.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in detection path '{path_id}' is a reserved device type")
    for path_id, path in scope.config.illumination.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in illumination path '{path_id}' is a reserved device type")
    return errors


def _build_stage(scope: Microscope) -> Stage:
    stage_cfg = scope.config.stage
    return Stage(
        x=scope.continuous_axes[stage_cfg.x],
        y=scope.continuous_axes[stage_cfg.y],
        z=scope.continuous_axes[stage_cfg.z],
    )

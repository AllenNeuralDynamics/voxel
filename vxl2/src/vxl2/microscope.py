"""Microscope — replaces VoxelRig with composition over rigur.Rig.

Typed device access via inherited handles (CameraHandle, DaqHandle,
ContinuousAxisHandle). Stage grouping, device validation, and profiles management
match VoxelRig's public API so downstream code (controllers, web services)
needs no changes.
"""

import logging
from dataclasses import dataclass

from rigur import DeviceHandle, Rig
from vxl2.config import MicroscopeConfig

from .axes import ContinuousAxisHandle
from .camera import CameraHandle
from .daq import DaqHandle
from .profiles import Profiles

logger = logging.getLogger(__name__)

HANDLE_MAP: dict[str, type[DeviceHandle]] = {
    "camera": CameraHandle,
    "daq": DaqHandle,
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

    Public API matches VoxelRig: ``cameras``, ``lasers``, ``daq``,
    ``stage``, ``profiles``, etc. Downstream code (controllers, web
    services) should work without changes.
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
        self.daq: DaqHandle | None = None
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
        self.daq = None
        await self._rig.close()


async def _categorize_handles(scope: Microscope) -> None:
    for uid, handle in scope.rig.devices.items():
        device_type = (await handle.interface()).type
        match device_type:
            case "camera":
                scope.cameras[uid] = CameraHandle.wrap(handle)
            case "daq":
                scope.daq = DaqHandle.wrap(handle)
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


def _validate_devices(scope: Microscope) -> None:  # noqa: C901
    errors: list[str] = []

    if scope.daq is None:
        errors.append(f"DAQ device '{scope.config.daq.device}' was not provisioned")

    camera_ids = set(scope.cameras.keys())
    detection_ids = set(scope.config.detection.keys())
    if missing := camera_ids - detection_ids:
        errors.append(f"Cameras without detection paths: {missing}")
    if invalid := detection_ids - camera_ids:
        errors.append(f"Detection paths referencing non-camera devices: {invalid}")

    laser_ids = set(scope.lasers.keys())
    illumination_ids = set(scope.config.illumination.keys())
    if missing := laser_ids - illumination_ids:
        errors.append(f"Lasers without illumination paths: {missing}")
    if invalid := illumination_ids - laser_ids:
        errors.append(f"Illumination paths referencing non-laser devices: {invalid}")

    if scope.daq is not None and scope.daq.uid != scope.config.daq.device:
        errors.append(f"DAQ device mismatch: expected '{scope.config.daq.device}', got '{scope.daq.uid}'")

    stage_cfg = scope.config.stage
    stage_axis_ids = {stage_cfg.x, stage_cfg.y, stage_cfg.z}
    if invalid_stage := stage_axis_ids - set(scope.continuous_axes.keys()):
        errors.append(f"Stage axes are not continuous_axis devices: {invalid_stage}")

    filter_wheel_ids = set(scope.config.filter_wheels)
    if invalid_fw := filter_wheel_ids - set(scope.discrete_axes.keys()):
        errors.append(f"Filter wheels are not discrete_axis devices: {invalid_fw}")

    reserved = camera_ids | laser_ids | filter_wheel_ids | stage_axis_ids
    if scope.daq is not None:
        reserved.add(scope.daq.uid)

    for path_id, path in scope.config.detection.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in detection path '{path_id}' is a reserved device type")

    for path_id, path in scope.config.illumination.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in illumination path '{path_id}' is a reserved device type")

    if errors:
        raise ValueError("Microscope device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


def _build_stage(scope: Microscope) -> Stage:
    stage_cfg = scope.config.stage
    return Stage(
        x=scope.continuous_axes[stage_cfg.x],
        y=scope.continuous_axes[stage_cfg.y],
        z=scope.continuous_axes[stage_cfg.z],
    )

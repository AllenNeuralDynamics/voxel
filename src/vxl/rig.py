"""Voxel's rigup extensions — VoxelNode and VoxelRig.

These two classes are the entire surface voxel adds on top of rigup:
 - ``VoxelNode`` teaches rigup how to build controllers/handles for voxel's
   device types (cameras, DAQs, continuous axes).
 - ``VoxelRig`` is a typed device registry + rigup lifecycle. It categorizes
   the handles rigup provisions into voxel-specific typed dicts, validates
   the config/hardware mapping, and owns the active-profile manager as
   ``rig.profiles`` (see ``vxl.profiles``). Preview, acquisition, and mode
   concerns live in peer controllers owned by the session orchestrator.

Usage:
    vxl-node <node_id> --rig <host[:port]>
"""

import argparse
import logging
import sys
from dataclasses import dataclass

import zmq.asyncio
from rigup.cluster import run_node_service
from rigup.device import Adapter, DeviceController

from rigup import Device, DeviceHandle, Rig, RigNode
from vxl.axes import ContinuousAxis, ContinuousAxisController, ContinuousAxisHandle
from vxl.camera.base import Camera, CameraController
from vxl.camera.handle import CameraHandle
from vxl.config import VoxelRigConfig
from vxl.daq import DaqController, DaqHandle, VoxelDaq
from vxl.device import DeviceType
from vxl.profiles import Profiles
from vxlib import configure_logging


class VoxelNode(RigNode):
    """Node service with Voxel-specific device support.

    Camera devices use CameraController for preview streaming.
    ContinuousAxis devices use ContinuousAxisController for TTL stepping.
    VoxelDaq devices use DaqController for task management.
    """

    @classmethod
    def create_controller(cls, device: Device) -> DeviceController:
        if isinstance(device, Camera):
            return CameraController(device)
        if isinstance(device, ContinuousAxis):
            return ContinuousAxisController(device, stream_interval=0.05)
        if isinstance(device, VoxelDaq):
            return DaqController(device)
        return super().create_controller(device)

    @classmethod
    def create_handle(cls, device_type: str, adapter: Adapter) -> DeviceHandle:
        match device_type:
            case DeviceType.CAMERA:
                return CameraHandle(adapter)
            case DeviceType.DAQ:
                return DaqHandle(adapter)
            case DeviceType.CONTINUOUS_AXIS:
                return ContinuousAxisHandle(adapter)
            case _:
                return super().create_handle(device_type, adapter)


@dataclass(frozen=True)
class VoxelStage:
    x: ContinuousAxisHandle
    y: ContinuousAxisHandle
    z: ContinuousAxisHandle

    @property
    def scanning_axis(self) -> ContinuousAxisHandle:
        return self.z


class VoxelRig(Rig):
    """Voxel-specific rigup.Rig — typed handles + validated wiring.

    The public surface is the typed device dicts (``cameras``, ``lasers``,
    ``daq``, ``stage``, ...) populated during ``start()``. Controllers consume
    this surface directly; they do not subclass or mutate the rig beyond what
    rigup itself exposes.
    """

    @classmethod
    def node_cls(cls) -> type[VoxelNode]:
        return VoxelNode

    def __init__(self, config: VoxelRigConfig, zctx: zmq.asyncio.Context | None = None) -> None:
        super().__init__(config=config, zctx=zctx)
        self.config: VoxelRigConfig = config
        self.cameras: dict[str, CameraHandle] = {}
        self.lasers: dict[str, DeviceHandle] = {}
        self.aotfs: dict[str, DeviceHandle] = {}
        self.continuous_axes: dict[str, ContinuousAxisHandle] = {}
        self.discrete_axes: dict[str, DeviceHandle] = {}
        self.fws: dict[str, DeviceHandle] = {}
        self.daq: DaqHandle | None = None
        self.stage: VoxelStage
        self.profiles: Profiles = Profiles(self)

    async def _on_start_complete(self) -> None:
        await _categorize_handles(self)
        _validate_devices(self)
        self.stage = _build_stage(self)
        await self.profiles.open()

    async def close(self) -> None:
        """Close ``profiles`` before rigup tears down device handles."""
        await self.profiles.close()
        await super().close()


async def _categorize_handles(rig: VoxelRig) -> None:
    for uid, handle in rig.handles.items():
        match await handle.device_type():
            case DeviceType.CAMERA:
                if not isinstance(handle, CameraHandle):
                    raise TypeError(f"Expected CameraHandle for {uid}, got {type(handle)}")
                rig.cameras[uid] = handle
            case DeviceType.DAQ:
                if not isinstance(handle, DaqHandle):
                    raise TypeError(f"Expected DaqHandle for {uid}, got {type(handle)}")
                rig.daq = handle
            case DeviceType.LASER:
                rig.lasers[uid] = handle
            case DeviceType.AOTF:
                rig.aotfs[uid] = handle
            case DeviceType.CONTINUOUS_AXIS:
                if not isinstance(handle, ContinuousAxisHandle):
                    raise TypeError(f"Expected ContinuousAxisHandle for {uid}, got {type(handle)}")
                rig.continuous_axes[uid] = handle
            case DeviceType.DISCRETE_AXIS:
                rig.discrete_axes[uid] = handle

    for fw_id in rig.config.filter_wheels:
        if fw_id in rig.handles:
            rig.fws[fw_id] = rig.handles[fw_id]


def _validate_devices(rig: VoxelRig) -> None:  # noqa: C901 - validates many device types
    errors: list[str] = []

    if rig.daq is None:
        errors.append(f"DAQ device '{rig.config.daq.device}' was not provisioned")

    camera_ids = set(rig.cameras.keys())
    detection_ids = set(rig.config.detection.keys())

    if missing := camera_ids - detection_ids:
        errors.append(f"Cameras without detection paths: {missing}")
    if invalid := detection_ids - camera_ids:
        errors.append(f"Detection paths referencing non-camera devices: {invalid}")

    laser_ids = set(rig.lasers.keys())
    illumination_ids = set(rig.config.illumination.keys())

    if missing := laser_ids - illumination_ids:
        errors.append(f"Lasers without illumination paths: {missing}")
    if invalid := illumination_ids - laser_ids:
        errors.append(f"Illumination paths referencing non-laser devices: {invalid}")

    if rig.daq is not None and rig.daq.uid != rig.config.daq.device:
        errors.append(f"DAQ device mismatch: expected '{rig.config.daq.device}', got '{rig.daq.uid}'")

    stage_axis_ids = {rig.config.stage.x, rig.config.stage.y, rig.config.stage.z}
    if invalid_stage := stage_axis_ids - set(rig.continuous_axes.keys()):
        errors.append(f"Stage axes are not CONTINUOUS_AXIS devices: {invalid_stage}")

    filter_wheel_ids = set(rig.config.filter_wheels)
    if invalid_fw := filter_wheel_ids - set(rig.discrete_axes.keys()):
        errors.append(f"Filter wheels are not DISCRETE_AXIS devices: {invalid_fw}")

    reserved = camera_ids | laser_ids | filter_wheel_ids | stage_axis_ids
    if rig.daq is not None:
        reserved.add(rig.daq.uid)

    for path_id, path in rig.config.detection.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in detection path '{path_id}' is a reserved device type")

    for path_id, path in rig.config.illumination.items():
        for aux in path.aux_devices:
            if aux in reserved:
                errors.append(f"Aux device '{aux}' in illumination path '{path_id}' is a reserved device type")

    if errors:
        raise ValueError("Voxel device validation failed:\n" + "\n".join(f"  - {e}" for e in errors))


def _build_stage(rig: VoxelRig) -> VoxelStage:
    return VoxelStage(
        x=rig.continuous_axes[rig.config.stage.x],
        y=rig.continuous_axes[rig.config.stage.y],
        z=rig.continuous_axes[rig.config.stage.z],
    )


def _create_node_parser() -> argparse.ArgumentParser:
    """Create the argument parser for node CLI."""
    parser = argparse.ArgumentParser(
        prog="vxl-node",
        description="Voxel Node Service - Manage devices on a node",
    )
    parser.add_argument("node_id", type=str, help="Node identifier (e.g., camera_1)")
    parser.add_argument("--rig", type=str, required=True, help="Rig controller address (host or host:port)")
    parser.add_argument("--log-port", type=int, default=9001, help="Controller log port (default: 9001)")
    parser.add_argument("--start-port", type=int, default=10000, help="Starting port for device services")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def node_main() -> None:
    """Entry point for vxl-node CLI."""
    args = _create_node_parser().parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    configure_logging(level=log_level, fmt="%(message)s", datefmt="[%X]")
    log = logging.getLogger("vxl.node")

    # Parse host:port
    if ":" in args.rig:
        ctrl_host, port_str = args.rig.split(":", 1)
        try:
            ctrl_port = int(port_str)
        except ValueError:
            log.exception("Invalid port in --rig argument: %s", port_str)
            sys.exit(1)
    else:
        ctrl_host = args.rig
        ctrl_port = 9000

    log.info("Starting Voxel Node: %s", args.node_id)
    log.info("Rig controller: %s:%d", ctrl_host, ctrl_port)

    run_node_service(
        node_id=args.node_id,
        ctrl_host=ctrl_host,
        ctrl_port=ctrl_port,
        log_port=args.log_port,
        start_port=args.start_port,
        service_cls=VoxelNode,
    )

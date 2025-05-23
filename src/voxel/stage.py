from dataclasses import dataclass

from voxel.devices.linear_axis import VoxelLinearAxis
from voxel.devices.rotation_axis import VoxelRotationAxis
from voxel.utils.log_config import get_component_logger
from voxel.utils.vec import Vec3D


@dataclass
class SpecimenStage:
    x: VoxelLinearAxis
    y: VoxelLinearAxis
    z: VoxelLinearAxis
    roll: VoxelRotationAxis | None = None  # Rotation around the x-axis
    pitch: VoxelRotationAxis | None = None  # Rotation around the y-axis
    yaw: VoxelRotationAxis | None = None  # Rotation around the z-axis
    name: str = "Stage"

    def __post_init__(self) -> None:
        self.log = get_component_logger(self)

    @property
    def position_mm(self) -> Vec3D[float]:
        return Vec3D(self.x.position_mm, self.y.position_mm, self.z.position_mm)

    @property
    def position_deg(self) -> Vec3D:
        if self.roll is None or self.pitch is None or self.yaw is None:
            return Vec3D(0, 0, 0)
        return Vec3D(
            self.roll.position_deg or 0,
            self.pitch.position_deg or 0,
            self.yaw.position_deg or 0,
        )

    def move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        roll: float | None = None,
        pitch: float | None = None,
        yaw: float | None = None,
        wait: bool = False,
    ) -> None:
        """Move stage to specified positions"""
        linear_zipped = zip([x, y, z], [self.x, self.y, self.z])
        moved_linear = False
        moved_rotational = False

        for arg, axis in linear_zipped:
            if arg is not None and axis is not None:
                axis.position_mm = arg
                moved_linear = True

        rotational_zipped = zip([roll, pitch, yaw], [self.roll, self.pitch, self.yaw])
        for arg, axis in rotational_zipped:
            if arg is not None and axis is not None:
                axis.position_deg = arg
                moved_rotational = True

        if wait:
            for axis in [self.x, self.y, self.z, self.roll, self.pitch, self.yaw]:
                if axis is not None:
                    axis.await_movement()

        if moved_linear:
            self.log.info(f"Moved stage to {self.position_mm.to_str()} mm")
        if moved_rotational:
            self.log.info(f"Moved stage to {self.position_deg.to_str()} degrees")

    def rotate_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        wait: bool = False,
    ) -> None:
        rotational_zipped = zip([x, y, z], [self.roll, self.pitch, self.yaw])
        moved = False
        for arg, axis in rotational_zipped:
            if arg is not None and axis is not None:
                axis.position_deg = arg
                moved = True
        if wait:
            for axis in [self.roll, self.pitch, self.yaw]:
                if axis is not None:
                    axis.await_movement()
        if moved:
            self.log.info(f"Moved stage to {self.position_deg.to_str()} degrees")

    @property
    def limits_mm(self) -> tuple[Vec3D, Vec3D]:
        z_limits = (self.z.lower_limit_mm, self.z.upper_limit_mm) if self.z is not None else (0, 0)
        lower_limits = Vec3D(self.x.lower_limit_mm, self.y.lower_limit_mm, z_limits[0])
        upper_limits = Vec3D(self.x.upper_limit_mm, self.y.upper_limit_mm, z_limits[1])
        return lower_limits, upper_limits

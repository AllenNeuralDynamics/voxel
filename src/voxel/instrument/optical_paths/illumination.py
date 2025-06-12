from voxel.devices.base import VoxelDevice
from voxel.devices.interfaces.laser import VoxelLaser
from voxel.utils.log_config import get_component_logger


class IlluminationPath:
    def __init__(self, laser: VoxelLaser, aux_devices: list[VoxelDevice]) -> None:
        self._laser = laser
        self._aux_devices = {device.name: device for device in aux_devices}
        self.log = get_component_logger(self)

    @property
    def laser(self) -> VoxelLaser:
        return self._laser

    @property
    def aux_devices(self) -> dict[str, VoxelDevice]:
        return self._aux_devices

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        """Return all devices in the illumination unit."""
        return {**self.aux_devices, self.laser.name: self.laser}

    @property
    def name(self) -> str:
        return f"{self.laser.name} unit"

    def enable(self) -> None:
        """Enable the laser in the illumination unit."""
        self.laser.enable()

    def disable(self) -> None:
        """Disable the laser in the illumination unit."""
        self.laser.disable()

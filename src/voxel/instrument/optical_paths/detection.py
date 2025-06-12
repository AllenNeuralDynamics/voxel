from voxel.devices.base import VoxelDevice
from voxel.devices.interfaces.camera import VoxelCamera
from voxel.devices.interfaces.filter_wheel import VoxelFilterWheel
from voxel.pipeline.common import IImagingPipeline
from voxel.utils.log_config import get_component_logger


class DetectionPath:
    def __init__(
        self, pipeline: IImagingPipeline, filter_wheels: list[VoxelFilterWheel], aux_devices: list[VoxelDevice]
    ) -> None:
        self._pipeline = pipeline
        self._filter_wheels = {fw.name: fw for fw in filter_wheels}
        self._aux_devices = {device.name: device for device in aux_devices}
        self.log = get_component_logger(self)

    @property
    def pipeline(self) -> IImagingPipeline:
        return self._pipeline

    @property
    def camera(self) -> VoxelCamera:
        return self._pipeline.camera

    @property
    def filter_wheels(self) -> dict[str, VoxelFilterWheel]:
        return self._filter_wheels

    @property
    def aux_devices(self) -> dict[str, VoxelDevice]:
        return self._aux_devices

    @property
    def devices(self) -> dict[str, VoxelDevice]:
        """Return all devices in the detection unit."""
        return {**self.filter_wheels, **self.aux_devices, self.camera.name: self.camera}

    @property
    def name(self) -> str:
        return f"{self.camera.name} unit"

    def set_filters(self, filters: dict[str, str]) -> None:
        """Set the filters for the filter wheels in the detection unit."""
        for fw_name, filter_name in filters.items():
            if fw_name not in self.filter_wheels:
                raise ValueError(f"Filter wheel {fw_name} not found in detection unit {self.name}.")
            self.filter_wheels[fw_name].set_filter(filter_name)
            self.log.info(f"Set filter '{filter_name}' on filter wheel '{fw_name}' in detection unit '{self.name}'.")

    def validate_filters(self, filters: dict[str, str]) -> dict[str, str]:
        """Validate the filter assignments against the available filter wheels."""
        errors = []
        for wheel_name, filter_name in filters.items():
            if wheel_name not in self.filter_wheels:
                errors.append(f"Filter wheel '{wheel_name}' not found in the detection unit.")
            elif filter_name not in self.filter_wheels[wheel_name].filters.values():
                errors.append(f"Filter '{filter_name}' not found in filter wheel '{wheel_name}'.")

        if errors:
            raise ValueError("Invalid filter assignments:\n" + "\n".join(errors))
        return filters

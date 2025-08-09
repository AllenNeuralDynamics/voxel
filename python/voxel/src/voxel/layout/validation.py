from collections.abc import Sequence
from typing import TYPE_CHECKING

from voxel.devices import VoxelCamera, VoxelFilterWheel, VoxelLaser, VoxelLinearAxis
from voxel.reporting.errors import ErrorInfo

from .models import LayoutDefinition

if TYPE_CHECKING:
    from voxel.devices.base import VoxelDevice


class LayoutValidator:
    """Validates instrument layout definitions against available devices."""

    @staticmethod
    def validate_layout(layout: LayoutDefinition, devices: dict[str, "VoxelDevice"]) -> Sequence[ErrorInfo]:
        """Validate the layout definition and return a sequence of layout-specific errors."""
        validator = LayoutValidator()
        return validator._validate(layout, devices)

    def _validate(self, layout: LayoutDefinition, devices: dict[str, "VoxelDevice"]) -> list[ErrorInfo]:
        """Internal validation method."""
        # Get device type mappings
        all_device_ids = set(devices.keys())
        camera_ids = set(self._get_devices_of_type(devices, VoxelCamera).keys())
        laser_ids = set(self._get_devices_of_type(devices, VoxelLaser).keys())
        filter_wheel_ids = set(self._get_devices_of_type(devices, VoxelFilterWheel).keys())
        linear_axis_ids = set(self._get_devices_of_type(devices, VoxelLinearAxis).keys())
        rotational_axis_ids = linear_axis_ids  # use linear for now

        errors = []

        # Validate each component
        errors.extend(self._validate_stage(layout, linear_axis_ids, rotational_axis_ids))

        valid_stage_axis_ids = self._get_valid_stage_axis_ids(layout, linear_axis_ids, rotational_axis_ids)
        allowed_aux_devices = all_device_ids - (camera_ids | laser_ids | filter_wheel_ids | valid_stage_axis_ids)

        errors.extend(self._validate_illumination(layout, laser_ids, allowed_aux_devices))
        errors.extend(self._validate_detection(layout, camera_ids, filter_wheel_ids, allowed_aux_devices))

        return errors

    def _validate_stage(
        self, layout: LayoutDefinition, linear_axis_ids: set[str], rotational_axis_ids: set[str]
    ) -> list[ErrorInfo]:
        """Validate stage device configuration."""
        errors = []

        # Check required linear axes
        listed_linear_axes = {layout.stage.x, layout.stage.y, layout.stage.z}
        if missing_linear_axes := listed_linear_axes - linear_axis_ids:
            for axis in missing_linear_axes:
                errors.append(
                    ErrorInfo(
                        name=f"stage_axis_{axis}",
                        category="stage_device_missing",
                        message=f"Linear axis '{axis}' not found in devices",
                    )
                )

        # Check optional rotational axes
        listed_rotational_axes = {
            axis for axis in [layout.stage.roll, layout.stage.pitch, layout.stage.yaw] if axis is not None
        }
        if missing_rotational_axes := listed_rotational_axes - rotational_axis_ids:
            for axis in missing_rotational_axes:
                errors.append(
                    ErrorInfo(
                        name=f"stage_axis_{axis}",
                        category="stage_axis_missing",
                        message=f"Rotational axis '{axis}' not found in devices",
                    )
                )

        return errors

    def _validate_illumination(
        self, layout: LayoutDefinition, laser_ids: set[str], allowed_aux_devices: set[str]
    ) -> list[ErrorInfo]:
        """Validate illumination path configuration."""
        errors = []

        # Check illumination paths have corresponding lasers
        illumination_path_ids = set(layout.illumination.keys())
        if paths_without_laser := illumination_path_ids - laser_ids:
            for path in paths_without_laser:
                errors.append(
                    ErrorInfo(
                        name=f"illumination_path_{path}",
                        category="illumination_device_missing",
                        message=f"Illumination path '{path}' has no corresponding laser device",
                    )
                )

        # Check all lasers have illumination paths
        if lasers_without_path := laser_ids - illumination_path_ids:
            for laser in lasers_without_path:
                errors.append(
                    ErrorInfo(
                        name=f"laser_{laser}",
                        category="illumination_device_missing",
                        message=f"Laser '{laser}' is missing illumination path",
                    )
                )

        # Check auxiliary devices in illumination paths
        listed_aux_device_ids = {dev for path in layout.illumination.values() for dev in path.aux_devices}
        if disallowed_aux_device := listed_aux_device_ids - allowed_aux_devices:
            for device in disallowed_aux_device:
                errors.append(
                    ErrorInfo(
                        name=f"illumination_aux_{device}",
                        category="illumination_aux_missing",
                        message=f"Auxiliary device '{device}' not allowed in illumination paths",
                    )
                )

        return errors

    def _validate_detection(
        self, layout: LayoutDefinition, camera_ids: set[str], filter_wheel_ids: set[str], allowed_aux_devices: set[str]
    ) -> list[ErrorInfo]:
        """Validate detection path configuration."""
        errors = []

        # Check detection paths have corresponding cameras
        detection_path_ids = set(layout.detection.keys())
        if paths_without_camera := detection_path_ids - camera_ids:
            for path in paths_without_camera:
                errors.append(
                    ErrorInfo(
                        name=f"detection_path_{path}",
                        category="detection_device_missing",
                        message=f"Detection path '{path}' has no corresponding camera device",
                    )
                )

        # Check all cameras have detection paths
        if cameras_without_path := camera_ids - detection_path_ids:
            for camera in cameras_without_path:
                errors.append(
                    ErrorInfo(
                        name=f"camera_{camera}",
                        category="detection_device_missing",
                        message=f"Camera '{camera}' is missing detection path",
                    )
                )

        # Check filter wheels exist
        listed_filter_wheel_ids = {dev for path in layout.detection.values() for dev in path.filter_wheels}
        if invalid_filter_wheels := listed_filter_wheel_ids - filter_wheel_ids:
            for fw in invalid_filter_wheels:
                errors.append(
                    ErrorInfo(
                        name=f"filter_wheel_{fw}",
                        category="detection_filter_wheel_missing",
                        message=f"Filter wheel '{fw}' not found in devices",
                    )
                )

        # Check auxiliary devices in detection paths
        listed_aux_device_ids = {dev for path in layout.detection.values() for dev in path.aux_devices}
        if disallowed_aux_device := listed_aux_device_ids - allowed_aux_devices:
            for device in disallowed_aux_device:
                errors.append(
                    ErrorInfo(
                        name=f"detection_aux_{device}",
                        category="device_type_mismatch",
                        message=f"Auxiliary device '{device}' not allowed in detection paths",
                    )
                )

        return errors

    def _get_valid_stage_axis_ids(
        self, layout: LayoutDefinition, linear_axis_ids: set[str], rotational_axis_ids: set[str]
    ) -> set[str]:
        """Get the set of valid stage axis device IDs."""
        listed_linear_axes = {layout.stage.x, layout.stage.y, layout.stage.z}
        listed_rotational_axes = {
            axis for axis in [layout.stage.roll, layout.stage.pitch, layout.stage.yaw] if axis is not None
        }
        return (listed_linear_axes & linear_axis_ids) | (listed_rotational_axes & rotational_axis_ids)

    @staticmethod
    def _get_devices_of_type[T: "VoxelDevice"](devices: dict[str, "VoxelDevice"], device_type: type[T]) -> dict[str, T]:
        """Get all devices of a specific type."""
        return {uid: dev for uid, dev in devices.items() if isinstance(dev, device_type)}

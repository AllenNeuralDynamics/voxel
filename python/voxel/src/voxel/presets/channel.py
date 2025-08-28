from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from voxel.reporting.errors import ErrorInfo

from .common import BaseDefinition, DefinitionsProviderBase, DefinitionStore, Repository

if TYPE_CHECKING:
    from voxel.instrument import Instrument


class ChannelDefinition(BaseDefinition):
    detection: str
    illumination: str
    filters: dict[str, str] = Field(default_factory=dict)

    def validate_definition(self, instrument: 'Instrument') -> Sequence[ErrorInfo]:
        errors = []

        if not instrument.layout:
            errors.append(
                ErrorInfo(
                    name=f'channel_{self.uid}',
                    category='layout_missing',
                    message='Layout is not defined in the context',
                ),
            )
            return errors

        if self.illumination not in instrument.layout.illumination:
            errors.append(
                ErrorInfo(
                    name=f'channel_{self.uid}_illumination',
                    category='illumination_path_not_found',
                    message=f"Illumination path '{self.illumination}' not found in layout",
                ),
            )

        if self.detection in instrument.layout.detection:
            detection_def = instrument.layout.detection[self.detection]
            for fw_id, filter_name in self.filters.items():
                if fw_id not in detection_def.filter_wheels:
                    errors.append(
                        ErrorInfo(
                            name=f'channel_{self.uid}_filter_wheel_{fw_id}',
                            category='filter_wheel_not_in_path',
                            message=f"Filter wheel '{fw_id}' not found in detection path '{self.detection}'",
                        ),
                    )
                    continue

                fw_device = instrument.filter_wheels.get(fw_id)
                if fw_device is None:
                    errors.append(
                        ErrorInfo(
                            name=f'channel_{self.uid}_filter_wheel_device_{fw_id}',
                            category='filter_wheel_device_not_found',
                            message=f"Filter wheel device '{fw_id}' not found in context",
                        ),
                    )
                    continue

                if filter_name not in fw_device.labels.values():
                    errors.append(
                        ErrorInfo(
                            name=f'channel_{self.uid}_filter_{filter_name}',
                            category='filter_not_in_wheel',
                            message=(
                                f"Filter '{filter_name}' not found in filter wheel '{fw_id}' "
                                f"for detection path '{self.detection}'"
                            ),
                        ),
                    )
        else:
            errors.append(
                ErrorInfo(
                    name=f'channel_{self.uid}_detection',
                    category='detection_path_not_found',
                    message=f"Detection path '{self.detection}' not found in layout",
                ),
            )

        return errors


class ChannelsStore(DefinitionStore[ChannelDefinition]):
    def __init__(self, persistence: Repository[ChannelDefinition] | None):
        super().__init__(ChannelDefinition, persistence)


class FilterWheelOption(BaseModel):
    """Filter wheel option for channel building."""

    uid: str
    filters: list[str]


class DetectionOption(BaseModel):
    """Detection option for channel building."""

    uid: str
    filter_wheels: list[FilterWheelOption] = Field(default_factory=list)


class IlluminationOption(BaseModel):
    """Illumination option for channel building."""

    uid: str


class ChannelBuildOptions(BaseModel):
    """Options available for building channels."""

    detections: list[DetectionOption] = Field(default_factory=list)
    illuminations: list[IlluminationOption] = Field(default_factory=list)


class ChannelsProvider(DefinitionsProviderBase[ChannelDefinition]):
    """Provides channels management with build options for detection and illumination paths."""

    def get_build_options(self) -> ChannelBuildOptions:
        """Generate channel build options based on available devices."""
        # Get filter wheels
        filter_wheels = [
            FilterWheelOption(uid=uid, filters=[name for name in fw.labels.values() if name is not None])
            for uid, fw in self._inst.filter_wheels.items()
        ]

        # Create detection options (one for each camera)
        detections = [DetectionOption(uid=camera_uid, filter_wheels=filter_wheels) for camera_uid in self._inst.cameras]

        # Create illumination options (one for each laser)
        illuminations = [IlluminationOption(uid=laser_uid) for laser_uid in self._inst.lasers]

        return ChannelBuildOptions(detections=detections, illuminations=illuminations)

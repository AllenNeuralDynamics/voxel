"""Core instrument management and validation."""

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

from voxel.devices import VoxelCamera, VoxelFilterWheel, VoxelLaser, VoxelLinearAxis
from voxel.devices.base import VoxelDevice
from voxel.factory import BuildSpecs, build_object_graph
from voxel.layout import LayoutDefinition, LayoutValidator
from voxel.presets import ChannelDefinition, ChannelsProvider, ProfileDefinition, ProfilesProvider, Repository
from voxel.reporting.errors import ErrorInfo
from voxel.runtime.imaging_runtime import ImagingRuntime
from voxel.runtime.preview.publisher import PreviewFramePublisher
from voxel.utils.log import VoxelLogging

if TYPE_CHECKING:
    from voxel.runtime.io.manager import IOManager


class InstrumentNodeType(StrEnum):
    LOCAL = 'local'
    REMOTE = 'remote'


class InstrumentNode:
    def __init__(
        self,
        uid: str,
        device_specs: 'BuildSpecs',
        preview: PreviewFramePublisher,
        io_manager: 'IOManager',
        node_type: InstrumentNodeType = InstrumentNodeType.LOCAL,
    ):
        self._uid = uid
        self._node_type = node_type
        self._device_specs = device_specs
        self._build_result = build_object_graph(device_specs, base_class=VoxelDevice)
        self._runtimes: dict[str, ImagingRuntime] = {}
        if devices := self._build_result.items:
            for uid, device in devices.items():
                if isinstance(device, VoxelCamera):
                    self._runtimes[uid] = ImagingRuntime(
                        camera=device,
                        io_manager=io_manager,
                        preview_pub=preview,
                    )

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def node_type(self) -> InstrumentNodeType:
        return self._node_type

    @property
    def devices(self) -> dict[str, 'VoxelDevice']:
        return self._build_result.items

    @property
    def build_errors(self) -> dict[str, ErrorInfo]:
        return self._build_result.errors

    @property
    def runtimes(self) -> dict[str, 'ImagingRuntime']:
        return self._runtimes

    def shutdown(self) -> None:
        """Shutdown the local instrument node."""
        self._runtimes.clear()
        print(f'LocalInstrumentNode {self._uid} shutdown complete.')


class InstrumentMetadata(BaseModel):
    uid: str
    model: str
    description: str | None = None
    version: str | None = None
    location: str | None = None


class Instrument:
    """Represents a complete instrument with devices, layout, and management capabilities."""

    def __init__(
        self,
        *,
        metadata: InstrumentMetadata,
        layout: 'LayoutDefinition',
        nodes: dict[str, InstrumentNode],
        channels_repository: 'Repository[ChannelDefinition]',
        profiles_repository: 'Repository[ProfileDefinition]',
    ) -> None:
        """Initialize the instrument with devices and layout."""
        self._nodes = nodes

        layout_errors = LayoutValidator.validate_layout(layout=layout, devices=self.devices)
        if layout_errors:
            # Group errors by type for better reporting
            error_details = {}
            for error in layout_errors:
                error_type = error.category
                if error_type not in error_details:
                    error_details[error_type] = []
                error_details[error_type].append(error.message)

            raise RuntimeError('Invalid instrument layout')

        self._logger = VoxelLogging.get_logger('instrument')

        self._layout_definition = layout
        self._metadata = metadata

        self._channels: ChannelsProvider = ChannelsProvider(self, channels_repository)
        self._profiles: ProfilesProvider = ProfilesProvider(self, profiles_repository)

    @property
    def metadata(self) -> InstrumentMetadata:
        """Get the instrument metadata."""
        return self._metadata

    @property
    def devices(self) -> dict[str, 'VoxelDevice']:
        """Get all device definitions."""
        return {uid: dev for node in self._nodes.values() for uid, dev in node.devices.items()}

    @property
    def runtimes(self) -> dict[str, InstrumentNode]:
        """Get all runtime definitions."""
        return {uid: node for uid, node in self._nodes.items() if node.runtimes}

    @property
    def cameras(self) -> dict[str, VoxelCamera]:
        """Get all camera devices."""
        return self.get_devices_of_type(device_type=VoxelCamera)

    @property
    def lasers(self) -> dict[str, VoxelLaser]:
        """Get all laser devices."""
        return self.get_devices_of_type(device_type=VoxelLaser)

    @property
    def linear_axes(self) -> dict[str, VoxelLinearAxis]:
        """Get all linear axis devices."""
        return self.get_devices_of_type(device_type=VoxelLinearAxis)

    @property
    def filter_wheels(self) -> dict[str, VoxelFilterWheel]:
        """Get all filter wheel devices."""
        return self.get_devices_of_type(device_type=VoxelFilterWheel)

    def get_devices_of_type[T: 'VoxelDevice'](self, device_type: type[T]) -> dict[str, T]:
        """Get all devices of a specific type."""
        return self._get_devices_of_type(devices=self.devices, device_type=device_type)

    @property
    def layout(self) -> LayoutDefinition:
        """Get the layout definition of the instrument."""
        return self._layout_definition

    @property
    def channels(self) -> ChannelsProvider:
        """Get the channels provider."""
        return self._channels

    @property
    def profiles(self) -> ProfilesProvider:
        """Get the profiles provider."""
        return self._profiles

    @staticmethod
    def _get_devices_of_type[T: 'VoxelDevice'](devices: dict[str, 'VoxelDevice'], device_type: type[T]) -> dict[str, T]:
        """Get all devices of a specific type."""
        return {uid: dev for uid, dev in devices.items() if isinstance(dev, device_type)}

    @staticmethod
    def validate_layout(layout: LayoutDefinition, devices: dict[str, 'VoxelDevice']) -> Sequence[ErrorInfo]:
        """Validate the layout definition and return a sequence of layout-specific errors.

        Note: This is a convenience method that delegates to LayoutValidator.
        """
        return LayoutValidator.validate_layout(layout, devices)

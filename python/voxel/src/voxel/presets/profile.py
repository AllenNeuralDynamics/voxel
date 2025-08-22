from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from voxel.reporting.errors import ErrorInfo

from .common import BaseDefinition, DefinitionsProviderBase, DefinitionStore, Repository

if TYPE_CHECKING:
    from voxel.instrument import Instrument


class ProfileDefinition(BaseDefinition):
    channels: list[str]

    def validate_definition(self, instrument: 'Instrument') -> Sequence[ErrorInfo]:
        errors = []

        if not instrument.layout:
            errors.append(
                ErrorInfo(
                    name=f'profile_{self.uid}',
                    category='layout_missing',
                    message='Layout is not defined in the context',
                ),
            )
            return errors

        for channel_id in self.channels:
            if inst_channel := instrument.channels.list().get(channel_id):
                chan_errors = inst_channel.validate_definition(instrument)
                if chan_errors:
                    # Aggregate channel errors into a profile error
                    error_messages = [err.message for err in chan_errors]
                    errors.append(
                        ErrorInfo(
                            name=f'profile_{self.uid}_channel_{channel_id}',
                            category='channel_validation_failed',
                            message=f"Channel '{channel_id}' validation failed: {error_messages}",
                            details={'channel_errors': chan_errors},
                        ),
                    )
            else:
                errors.append(
                    ErrorInfo(
                        name=f'profile_{self.uid}_channel_{channel_id}',
                        category='channel_not_found',
                        message=f"Channel '{channel_id}' not found in instrument",
                    ),
                )

        return errors


class ProfilesStore(DefinitionStore[ProfileDefinition]):
    def __init__(self, persistence: Repository[ProfileDefinition] | None):
        super().__init__(ProfileDefinition, persistence)


class ProfileBuildOptions(BaseModel):
    """Options for building profiles."""

    channels: list[str] = Field(default_factory=list)


class ProfilesProvider(DefinitionsProviderBase[ProfileDefinition]):
    """Provides profiles management with build options based on available channels."""

    def get_build_options(self) -> ProfileBuildOptions:
        """Generate profile build options based on available channels."""
        available_channels = list(self._cache.keys())
        return ProfileBuildOptions(channels=available_channels)

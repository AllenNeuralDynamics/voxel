from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from voxel.presets.channel import ChannelDefinition
from voxel.presets.common import Repository
from voxel.presets.profile import ProfileDefinition


class InstrumentConfigLoader(ABC):
    """Abstract base class for loading instrument configurations."""

    @property
    @abstractmethod
    def instrument_id(self) -> str:
        """Get the unique identifier for the instrument."""
        pass

    @abstractmethod
    def get_system_config(self) -> dict[str, Any]:
        """Get the loaded instrument configuration."""
        pass

    @abstractmethod
    def get_channel_repository(self) -> Repository[ChannelDefinition]:
        """Get the channel repository."""
        pass

    @abstractmethod
    def get_profile_repository(self) -> Repository[ProfileDefinition]:
        """Get the profile repository."""
        pass


class InstrumentDiscovery(ABC):
    """Abstract base class for discovering and parsing instrument configurations."""

    @abstractmethod
    def run_discovery(self) -> Mapping[str, "InstrumentConfigLoader"]:
        """Scan for instrument configurations and create launchers for each."""
        pass

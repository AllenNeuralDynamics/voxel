from abc import abstractmethod
from typing import Any, Dict

from ..base import VoxelDevice


class BaseTunableLens(VoxelDevice):

    @property
    @abstractmethod
    def mode(self) -> str:
        """Get the tunable lens control mode."""
        pass

    @mode.setter
    @abstractmethod
    def mode(self, mode: str):
        """Set the tunable lens control mode.
        :param mode: one of "internal" or "external".
        :type mode: str
        """
        pass

    @property
    @abstractmethod
    def temperature_c(self) -> float:
        """Get the temperature in deg C."""
        pass

    @abstractmethod
    def log_metadata(self) -> Dict[str, Any]:
        """Log metadata about the tunable lens."""
        pass

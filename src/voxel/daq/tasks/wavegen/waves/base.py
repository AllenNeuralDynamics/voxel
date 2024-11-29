from dataclasses import dataclass

import numpy as np

WaveformData = np.ndarray


@dataclass
class WaveGenTiming:
    """Timing parameters for a DAQ task."""

    sampling_rate: float
    period_ms: float

    @property
    def samples_per_period(self) -> int:
        """The number of samples per period. Determines the buffer size created for continuous tasks."""
        return int(self.sampling_rate * self.period_ms / 1000)

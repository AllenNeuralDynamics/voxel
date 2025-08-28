from abc import ABC, abstractmethod

import numpy as np


class FrameGenerator(ABC):
    """Abstract base class for all frame generators."""

    @abstractmethod
    def generate(self, nframes: int = 1) -> np.ndarray:
        """Generates a specified number of frames.

        :param nframes: The number of frames to generate.
        :return: A numpy array with shape (nframes, height, width).
        """

    def __iter__(self):
        """Allows the generator to be used in a loop, yielding single frames."""
        self._iter_index = 0
        return self

    def __next__(self):
        # This basic implementation is for stateless generators.
        # It can be overridden for more complex, stateful iteration.
        return self.generate(nframes=1)[0]

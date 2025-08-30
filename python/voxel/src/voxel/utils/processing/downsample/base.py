from abc import abstractmethod

import numpy as np
from voxel.utils.log import VoxelLogging


class BaseDownSample:
    """Base class for image downsampling.

    :param image: Input image
    :type image: np.ndarray
    """

    def __init__(self, binning: int) -> None:
        self._binning = binning
        self.log = VoxelLogging.get_logger(f'{__name__}.{self.__class__.__name__}')

    @abstractmethod
    def run(self, image: np.ndarray) -> np.ndarray:
        """Run function for image downsampling.

        :param image: Input image
        :type image: np.ndarray
        """

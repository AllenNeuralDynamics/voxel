from abc import abstractmethod
from collections.abc import Callable

import numpy
from voxel.utils.log import VoxelLogging


class BaseDownSample:
    """
    Base class for image downsampling.
    """

    def __init__(self, binning: int) -> None:
        """
        Module for handling downsampling processes.

        :param binning: The binning factor for downsampling.
        :type binning: int
        """
        self._binning = binning
        self.log = VoxelLogging.get_logger(object=self)

    @abstractmethod
    def run(self, method: Callable[[numpy.ndarray], numpy.ndarray], image: numpy.ndarray) -> numpy.ndarray:
        """
        Run function for image downsampling.

        :param method: The downsampling method to use.
        :type method: Callable[[numpy.ndarray], numpy.ndarray]
        :param image: Input image
        :type image: numpy.ndarray
        :return: Downsampled image
        :rtype: numpy.ndarray
        """
        pass

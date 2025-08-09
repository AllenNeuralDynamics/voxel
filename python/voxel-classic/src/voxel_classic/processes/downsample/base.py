import logging
from abc import abstractmethod
from typing import Callable

import numpy


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
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

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

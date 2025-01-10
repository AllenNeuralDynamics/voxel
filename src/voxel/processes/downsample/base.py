import logging
from abc import abstractmethod

import numpy


class BaseDownSample:
    """
    Base class for image downsampling.

    :param image: Input image
    :type image: numpy.array
    """

    def __init__(self, binning: int) -> None:
        self._binning = binning
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def run(self, method, image: numpy.array):
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.array
        """
        pass

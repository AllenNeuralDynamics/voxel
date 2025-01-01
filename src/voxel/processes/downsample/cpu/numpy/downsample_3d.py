import numpy

from voxel.processes.downsample.base import BaseDownSample


class NPDownSample3D(BaseDownSample):
    """
    Voxel 3D downsampling with numpy.
    """

    def __init__(self, binning: int) -> None:
        """
        Module for handling 3D downsampling processes.

        :param binning: The binning factor for downsampling.
        :type binning: int
        :raises ValueError: If the binning factor is not valid.
        """
        super().__init__(binning)
        # downscaling factor
        if binning != 2:
            raise ValueError("cpu downsampling only supports binning=2")

    def run(self, image: numpy.ndarray) -> numpy.ndarray:
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.ndarray
        :return: Downsampled image
        :rtype: numpy.ndarray
        """
        downsampled_image = (
            image[0::2, 0::2, 0::2]
            + image[1::2, 0::2, 0::2]
            + image[0::2, 1::2, 0::2]
            + image[0::2, 0::2, 1::2]
            + image[1::2, 1::2, 0::2]
            + image[0::2, 1::2, 1::2]
            + image[1::2, 0::2, 1::2]
            + image[1::2, 1::2, 1::2]
        ) // 8
        return downsampled_image
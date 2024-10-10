import numpy

from voxel.processes.downsample.base import BaseDownSample


class NPDownSample2D(BaseDownSample):
    """
    Voxel 2D downsampling with numpy.

    :param binning: Binning factor
    :type binning: int
    :raise ValueError: Invalid binning factor
    """

    def __init__(self, binning: int):
        super().__init__(binning)
        # downscaling factor
        if binning != 2:
            raise ValueError("cpu downsampling only supports binning=2")

    def run(self, image: numpy.array):
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.array
        :return: Downsampled image
        :rtype: numpy.array
        """

        downsampled_image = (
            image[0::2, 0::2]
            + image[1::2, 0::2]
            + image[0::2, 1::2]
            + image[1::2, 1::2]
        ) // 4
        return downsampled_image

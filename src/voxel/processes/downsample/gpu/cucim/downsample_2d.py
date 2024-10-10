import cupy
import numpy
from cucim.skimage.transform import downscale_local_mean

from voxel.processes.downsample.base import BaseDownSample


class CucimDownSample2D(BaseDownSample):
    """
    Voxel 2D downsampling with cucim.

    :param binning: Binning factor
    :type binning: int
    """

    def __init__(self, binning: int):
        super().__init__(binning)

    def run(self, image: numpy.array):
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.array
        :return: Downsampled image
        :rtype: numpy.array
        """

        # convert numpy to cupy array
        image = cupy.asarray(image)
        downsampled_image = downscale_local_mean(image, factors=(self._binning, self._binning))
        return downsampled_image
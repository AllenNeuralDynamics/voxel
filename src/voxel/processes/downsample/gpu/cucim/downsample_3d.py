import cupy
import numpy
from cucim.skimsage.transform import downscale_local_mean

from voxel.processes.downsample.base import BaseDownSample


class CucimDownSample3D(BaseDownSample):
    """
    Voxel 3D downsampling with cucim.

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
        downsampled_image = downscale_local_mean(image, factors=(self._binning, self._binning, self._binning))
        return downsampled_image

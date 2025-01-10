import numpy
import tensorstore as ts

from voxel.processes.downsample.base import BaseDownSample


class TSDownSample2D(BaseDownSample):
    """
    Voxel 2D downsampling with tensorstore.

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

        downsampled_image = (
            ts.downsample(
                ts.array(image),
                downsample_factors=[self._binning, self._binning],
                method="mean",
            )
            .read()
            .result()
        )
        return downsampled_image

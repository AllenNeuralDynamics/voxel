import numpy
import tensorstore as ts

from voxel_classic.processes.downsample.base import BaseDownSample


class TSDownSample3D(BaseDownSample):
    """
    Voxel 3D downsampling with tensorstore.
    """

    def __init__(self, binning: int) -> None:
        """
        Module for handling 3D downsampling processes.

        :param binning: The binning factor for downsampling.
        :type binning: int
        :raises ValueError: If the binning factor is not valid.
        """
        super().__init__(binning)

    def run(self, image: numpy.ndarray) -> numpy.ndarray:
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.ndarray
        :return: Downsampled image
        :rtype: numpy.ndarray
        """
        downsampled_image = (
            ts.downsample(
                ts.array(image),
                downsample_factors=[self._binning, self._binning, self._binning],
                method="mean",
            )
            .read()
            .result()
        )
        return downsampled_image

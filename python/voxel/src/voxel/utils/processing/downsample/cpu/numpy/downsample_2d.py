import numpy as np
from voxel.utils.processing.downsample.base import BaseDownSample


class NPDownSample2D(BaseDownSample):
    """Voxel 2D downsampling with np.

    :param binning: Binning factor
    :type binning: int
    :raise ValueError: Invalid binning factor
    """

    def __init__(self, binning: int) -> None:
        super().__init__(binning)
        # downscaling factor
        if binning != 2:
            raise ValueError('cpu downsampling only supports binning=2')

    def run(self, image: np.ndarray) -> np.ndarray:
        """Run function for image downsampling.

        :param image: Input image
        :type image: np.ndarray
        :return: Downsampled image
        :rtype: np.ndarray
        """
        return (image[0::2, 0::2] + image[1::2, 0::2] + image[0::2, 1::2] + image[1::2, 1::2]) // 4

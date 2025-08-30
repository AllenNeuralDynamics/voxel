import numpy
import pyclesperanto as cle
from exaspim_control.voxel_classic.processes.downsample.base import BaseDownSample


class CLEDownSample3D(BaseDownSample):
    """Voxel 3D downsampling with pyclesperanto."""

    def __init__(self, binning: int) -> None:
        """Module for handling 3D downsampling processes.

        :param binning: The binning factor for downsampling.
        :type binning: int
        :raises ValueError: If the binning factor is not valid.
        """
        super().__init__(binning)
        # get gpu device
        self._device = cle.select_device()

    def run(self, image: numpy.ndarray) -> numpy.ndarray:
        """Run function for image downsampling.

        :param image: Input image
        :type image: numpy.ndarray
        :return: Downsampled image
        :rtype: numpy.ndarray
        """
        # move image to gpu
        input_image = cle.push(image)
        # run operation
        downsampled_image = cle.scale(
            input_image,
            factor_x=1 / self._binning,
            factor_y=1 / self._binning,
            factor_z=1 / self._binning,
            device=self._device,
            resize=True,
        )
        # move image off gpu and return
        return cle.pull(downsampled_image)

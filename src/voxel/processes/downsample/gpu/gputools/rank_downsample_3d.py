from numbers import Number
from pathlib import Path

import numpy
from gputools import OCLArray, OCLProgram
from mako.template import Template

from voxel.processes.downsample.base import BaseDownSample


class GPUToolsDownSample3D(BaseDownSample):
    """
    Voxel 3D rank order downsampling with gputools.

    :param binning: Binning factor
    :type binning: int
    :param rank: Rank order
    :param data_type: Data type (uint8 or uint16)
    :type data_type: str

    Rank of element to retain (if None: median)
    If rank=0 then the minimum is returned
    If rank = size[0] x size[1] x size[2] - 1 (or -1) then the maximum is returned
    """

    def __init__(self, binning: int, rank=None, data_type=None):
        super().__init__(binning)
        self._rank = None

        self._rank = rank
        # opencl kernel
        with open(Path(__file__).absolute().parent/"rank_downscale_3d.cl", "r") as f:
            self._kernel = Template(f.read())

        # set binning
        if isinstance(binning, Number):
            binning = (int(binning),)*3

        if len(binning) != 3:
            raise ValueError("size has to be a tuple of 3 ints")

        self._binning = tuple(map(int, binning))

        # determine rank order
        if self._rank is None:
            self._rank = numpy.prod(self._binning) // 2
        else:
            self._rank = self._rank % numpy.prod(self._binning)

        # determine gpu data type
        if data_type == 'uint16':
            gpu_dtype = 'ushort'
        elif data_type == 'uint8':
            gpu_dtype = 'uchar'
        else:
            raise ValueError(f"Data type {data_type} not supported")

        rendered = self._kernel.render(DTYPE=gpu_dtype,
                                       FSIZE_X=self._binning[2],
                                       FSIZE_Y=self._binning[1],
                                       FSIZE_Z=self._binning[0],
                                       CVAL=0)

        self._prog = OCLProgram(src_str=rendered)

    def run(self, image: numpy.array):
        """
        Run function for rank order image downsampling.

        :param image: Input image
        :type image: numpy.array
        :return: Downsampled image
        :rtype: numpy.array
        """

        x_g = OCLArray.from_array(image)
        y_g = OCLArray.empty(tuple(s0//s for s, s0 in zip(self._binning, x_g.shape)), x_g.dtype)

        self._prog.run_kernel("rank_3", y_g.shape[::-1], None, x_g.data, y_g.data,
                              numpy.int32(x_g.shape[2]), numpy.int32(x_g.shape[1]),
                              numpy.int32(x_g.shape[0]), numpy.int32(self._rank))
        return y_g.get()


if __name__ == "__main__":
    x = numpy.random.randint(3, 11, size=(2048, 2048, 1)).astype(numpy.uint16)
    downsample = GPUToolsDownSample3D(binning=(2, 2, 1), rank=-2, data_type='uint16')
    y = downsample.run(x)

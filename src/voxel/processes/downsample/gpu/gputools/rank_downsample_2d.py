from numbers import Number

import numpy
from gputools import OCLArray, OCLProgram
from gputools.convolve._abspath import abspath
from gputools.core.ocltypes import cl_buffer_datatype_dict
from mako.template import Template

from voxel.processes.downsample.base import BaseDownSample


class GPUToolsRankDownSample2D(BaseDownSample):
    """
    Voxel rank order downsampling with gputools.

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

        self._binning = binning
        if isinstance(self._binning, Number):
            self._binning = (int(self._binning),) * 2

        self._rank = rank
        if self._rank is None:
            self._rank = numpy.prod(self._binning) // 2
        else:
            self._rank = self._rank % numpy.prod(self._binning)

        if data_type == "uint8":
            DTYPE = cl_buffer_datatype_dict[numpy.uint8]
        elif data_type == "uint16":
            DTYPE = cl_buffer_datatype_dict[numpy.uint16]
        else:
            raise ValueError("Invalid data type: {}".format(self._data_type))

        with open(abspath("kernels/rank_downscale.cl"), "r") as f:
            tpl = Template(f.read())

        rendered = tpl.render(DTYPE = DTYPE,
                              FSIZE_Z=0,
                              FSIZE_X=self._binning[1],
                              FSIZE_Y=self._binning[0],
                              CVAL = 0)  # constant value

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
        y_g = OCLArray.empty(tuple(s0 // s for s, s0 in zip(self._binning, x_g.shape)), x_g.dtype)

        self._prog.run_kernel(
            "rank_2",
            y_g.shape[::-1],
            None,
            x_g.data,
            y_g.data,
            numpy.int32(x_g.shape[1]),
            numpy.int32(x_g.shape[0]),
            numpy.int32(self._rank),
        )
        return y_g.get()

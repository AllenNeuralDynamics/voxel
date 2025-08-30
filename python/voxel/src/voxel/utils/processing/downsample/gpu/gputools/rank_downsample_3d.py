from pathlib import Path

import numpy as np
from gputools import OCLArray, OCLProgram
from mako.template import Template
from voxel.utils.processing.downsample.base import BaseDownSample


class GPUToolsDownSample3D(BaseDownSample):
    """Voxel 3D rank order downsampling with gputools.

    :param binning: Binning factor
    :type binning: int
    :param rank: Rank order
    :param data_type: Data type (uint8 or uint16)
    :type data_type: str

    Rank of element to retain (if None: median)
    If rank=0 then the minimum is returned
    If rank = size[0] x size[1] x size[2] - 1 (or -1) then the maximum is returned
    """

    def __init__(self, binning: int | tuple[int, int, int], rank: int | None = None, data_type: str | None = None):
        # set binning
        binning_tuple = binning if isinstance(binning, tuple) else (binning, binning, binning)
        super().__init__(binning_tuple[0])

        self._rank = rank or 0
        # opencl kernel
        with (Path(__file__).absolute().parent / 'rank_downscale_3d.cl').open() as f:
            self._kernel = Template(f.read())  # noqa: S702

        if len(binning_tuple) != 3:
            raise ValueError('size has to be a tuple of 3 ints')

        self._binning = tuple(map(int, binning_tuple))

        # determine rank order
        if self._rank is None:
            self._rank = np.prod(self._binning) // 2
        else:
            self._rank = self._rank % np.prod(self._binning)

        assert self._rank is not None

        # determine gpu data type
        if data_type == 'uint16':
            gpu_dtype = 'ushort'
        elif data_type == 'uint8':
            gpu_dtype = 'uchar'
        else:
            msg = f'Data type {data_type} not supported'
            raise ValueError(msg)

        rendered = self._kernel.render(
            DTYPE=gpu_dtype,
            FSIZE_X=self._binning[2],
            FSIZE_Y=self._binning[1],
            FSIZE_Z=self._binning[0],
            CVAL=0,
        )

        self._prog = OCLProgram(src_str=rendered)

    def run(self, image: np.ndarray):
        """Run function for rank order image downsampling.

        :param image: Input image
        :type image: np.ndarray
        :return: Downsampled image
        :rtype: np.ndarray
        """
        x_g = OCLArray.from_array(image)  # pyright: ignore[reportAttributeAccessIssue]
        y_g = OCLArray.empty(tuple(s0 // s for s, s0 in zip(self._binning, x_g.shape, strict=True)), x_g.dtype)  # pyright: ignore[reportAttributeAccessIssue]

        self._prog.run_kernel(
            'rank_3',
            y_g.shape[::-1],
            None,
            x_g.data,
            y_g.data,
            np.int32(x_g.shape[2]),
            np.int32(x_g.shape[1]),
            np.int32(x_g.shape[0]),
            np.int32(self._rank),
        )
        return y_g.get()


if __name__ == '__main__':
    rng = np.random.default_rng()
    x = rng.integers(3, 11, size=(2048, 2048, 1), dtype=np.uint16)
    downsample = GPUToolsDownSample3D(binning=(2, 2, 1), rank=-2, data_type='uint16')
    y = downsample.run(x)

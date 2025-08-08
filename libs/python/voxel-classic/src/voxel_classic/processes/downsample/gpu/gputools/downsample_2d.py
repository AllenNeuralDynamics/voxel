import numpy as np
from gputools import OCLArray, OCLProgram

from voxel_classic.processes.downsample.base import BaseDownSample


class GPUToolsDownSample2D(BaseDownSample):
    """
    Voxel 2D downsampling with gputools.
    """

    def __init__(self, binning: int, mode: str) -> None:
        """
        Module for handling 2D downsampling processes.

        :param binning: The binning factor for downsampling.
        :type binning: int
        :raises ValueError: If the binning factor is not valid.
        """
        super().__init__(binning)
        # opencl kernel
        if mode == "average":
            self._kernel = """
            __kernel void downsample2d(__global short * input,
                                    __global short * output){
            int i = get_global_id(0);
            int j = get_global_id(1);
            int Nx = get_global_size(0);
            int Ny = get_global_size(1);
            int res = 0;

            for (int m = 0; m < BLOCK; ++m)
                for (int n = 0; n < BLOCK; ++n)
                    res+=input[BLOCK*Nx*(BLOCK*j+m)+BLOCK*i+n];
            output[Nx*j+i] = (short)(res/BLOCK/BLOCK);
            }
            """
        elif mode == "sum":
            self._kernel = """
            __kernel void downsample2d(__global short * input,
                                    __global short * output){
            int i = get_global_id(0);
            int j = get_global_id(1);
            int Nx = get_global_size(0);
            int Ny = get_global_size(1);
            int res = 0;

            for (int m = 0; m < BLOCK; ++m)
                for (int n = 0; n < BLOCK; ++n)
                    res+=input[BLOCK*Nx*(BLOCK*j+m)+BLOCK*i+n];
            output[Nx*j+i] = (short)(res);
            }
            """
        else:
            raise ValueError(f"invalid mode: {mode}, mode must be 'average' or 'sum'")

        self._prog = OCLProgram(src_str=self._kernel, build_options=["-D", f"BLOCK={self._binning}"])

    def run(self, image: np.ndarray) -> np.ndarray:
        """
        Run function for image downsampling.

        :param image: Input image
        :type image: numpy.ndarray
        :return: Downsampled image
        :rtype: numpy.ndarray
        """
        x_g = OCLArray.from_array(image)
        y_g = OCLArray.empty(tuple(s // self._binning for s in image.shape), image.dtype)
        self._prog.run_kernel("downsample2d", y_g.shape[::-1], None, x_g.data, y_g.data)
        return y_g.get()

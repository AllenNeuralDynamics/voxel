from pathlib import Path

import numpy as np
import tifffile

from voxel.processes.max_projection.base import BaseMaxProjection


class GPUMaxProjection(BaseMaxProjection):
    """
    Voxel driver for the GPU max projection process.

    The process will save data to the following location

    path\\acquisition_name\\filename*

    :param path: Path for the data writer
    :type path: str
    """

    def __init__(self, path: str):
        super().__init__(path)

    def _run(self):
        # cannot pickle cle so import within run function()
        import pyclesperanto as cle

        # check if projection counts were set
        # if not, set to max possible values based on tile
        if self._x_projection_count_px is None:
            x_projection = False
        else:
            x_projection = True
            if self._x_projection_count_px < 0 or self._x_projection_count_px > self._column_count_px:
                raise ValueError(f"x projection must be > 0 and < {self._column_count_px}")
            x_index_list = np.arange(0, self._column_count_px, self._x_projection_count_px)
            if self._column_count_px not in x_index_list:
                x_index_list = np.append(x_index_list, self._column_count_px)
            self.mip_yz = np.zeros(
                (self._frame_count_px_px, self._row_count_px, len(x_index_list)),
                dtype=self._data_type,
            )
        if self._y_projection_count_px is None:
            y_projection = False
        else:
            y_projection = True
            if self._y_projection_count_px < 0 or self._y_projection_count_px > self._row_count_px:
                raise ValueError(f"y projection must be > 0 and < {self._row_count_px}")
            y_index_list = np.arange(0, self._row_count_px, self._y_projection_count_px)
            if self._row_count_px not in y_index_list:
                y_index_list = np.append(y_index_list, self._row_count_px)
            self.mip_xz = np.zeros(
                (self._frame_count_px_px, self._column_count_px, len(y_index_list)),
                dtype=self._data_type,
            )
        if self._z_projection_count_px is None:
            z_projection = False
        else:
            z_projection = True
            if self._z_projection_count_px < 0 or self._z_projection_count_px > self._frame_count_px_px:
                raise ValueError(f"z projection must be > 0 and < {self._frame_count_px}")
            self.mip_xy = np.zeros((self._row_count_px, self._column_count_px), dtype=self._data_type)

        frame_index = 0
        start_index = 0

        while frame_index < self._frame_count_px_px:
            # max project latest image
            if self.new_image.is_set():
                self.latest_img = np.ndarray(self.shm_shape, self._data_type, buffer=self.shm.buf)
                if z_projection:
                    # move images to gpu
                    latest_img = cle.push(self.latest_img)
                    mip_xy = cle.push(self.mip_xy)
                    # run operation
                    new_mip_xy = cle.maximum_images(latest_img, mip_xy)
                    # move image off gpu
                    self.mip_xy = cle.pull(new_mip_xy)
                    # if this projection thickness is complete or end of stack
                    chunk_index = frame_index % self._z_projection_count_px
                    if chunk_index == self._z_projection_count_px - 1 or frame_index == self._frame_count_px_px - 1:
                        end_index = int(frame_index + 1)
                        self.log.info(
                            f"saving {self.filename}_max_projection_xy_z_{start_index:06}_{end_index:06}.tiff"
                        )
                        tifffile.imwrite(
                            Path(
                                self.path,
                                self._acquisition_name,
                                f"{self.filename}_max_projection_xy_z_{start_index:06}_{end_index:06}.tiff",
                            ),
                            self.mip_xy,
                        )
                        # reset the xy mip
                        self.mip_xy = np.zeros(
                            (self._row_count_px, self._column_count_px),
                            dtype=self._data_type,
                        )
                        # set next start index to previous end index
                        start_index = end_index
                if x_projection:
                    for i in range(0, len(x_index_list) - 1):
                        self.mip_yz[frame_index, :, i] = np.max(
                            self.latest_img[:, x_index_list[i] : x_index_list[i + 1]],
                            axis=1,
                        )
                if y_projection:
                    for i in range(0, len(y_index_list) - 1):
                        self.mip_xz[frame_index, :, i] = np.max(
                            self.latest_img[y_index_list[i] : y_index_list[i + 1], :],
                            axis=0,
                        )
                frame_index += 1
                self.new_image.clear()
        if x_projection:
            for i in range(0, len(x_index_list) - 1):
                start_index = x_index_list[i]
                end_index = x_index_list[i + 1]
                self.log.info(f"saving {self.filename}_max_projection_yz_x_{start_index:06}_{end_index:06}.tiff")
                tifffile.imwrite(
                    Path(
                        self.path,
                        self._acquisition_name,
                        f"{self.filename}_max_projection_yz_x_{start_index:06}_{end_index:06}.tiff",
                    ),
                    self.mip_yz[:, :, i],
                )
        if y_projection:
            for i in range(0, len(y_index_list) - 1):
                start_index = y_index_list[i]
                end_index = y_index_list[i + 1]
                self.log.info(f"saving {self.filename}_max_projection_xz_y_{start_index:06}_{end_index:06}.tiff")
                tifffile.imwrite(
                    Path(
                        self.path,
                        self._acquisition_name,
                        f"{self.filename}_max_projection_xz_y_{start_index:06}_{end_index:06}.tiff",
                    ),
                    self.mip_xz[:, :, i],
                )

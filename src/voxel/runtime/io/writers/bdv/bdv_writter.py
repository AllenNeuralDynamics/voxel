from enum import StrEnum
from math import ceil
from typing import TYPE_CHECKING

import numpy as np

from ..base import VoxelWriter, WriterConfig

from .sdk import npy2bdv

if TYPE_CHECKING:
    from pathlib import Path

CHUNK_SIZE_PX = 64

B3D_QUANT_SIGMA = 1  # quantization step
B3D_COMPRESSION_MODE = 1
B3D_BACKGROUND_OFFSET = 0  # ADU
B3D_GAIN = 2.1845  # ADU/e-
B3D_READ_NOISE = 1.5  # e-

B3D_COMPRESSION_OPTS = (
    int(B3D_QUANT_SIGMA * 1000),
    B3D_COMPRESSION_MODE,
    int(B3D_GAIN),
    int(B3D_BACKGROUND_OFFSET),
    int(B3D_READ_NOISE * 1000),
)


class BdvCompression(StrEnum):
    NONE = "none"
    GZIP = "gzip"
    LZF = "lzf"
    B3D = "b3d"


# TODO: Review this class and test it
# Compare with previous implementation in ./sdk/bdv_prev.py


class BdvWriter(VoxelWriter):
    def __init__(self, *, name: str = "bdv_writer", theta_deg: float = 0.0) -> None:
        super().__init__(name)
        self._theta_deg = theta_deg

        self._tiles_set = set()
        self._channels_set = set()

        self._tile_idx = 0
        self._tile_shape_dict = {}

        self._affine_deskew_dict = {}
        self._affine_scale_dict = {}
        self._affine_shift_dict = {}

        # properties
        self._output_file: Path
        self._npy2bdv: npy2bdv.BdvWriter
        self._compression: BdvCompression = BdvCompression.NONE

    @property
    def compression(self) -> None | str:
        """Get the compression codec of the writer.

        :return: Compression codec
        :rtype: str
        """

        if self._compression == "none":
            return None
        return str(self._compression)

    @compression.setter
    def compression(self, compression: str | None) -> None:
        """Set the compression codec of the writer.

        :param value: Compression codec
        * **gzp**
        * **lzf**
        * **b3d**
        * **none**
        :type value: str
        :raises ValueError: Invalid compression codec
        :raises ValueError: B3D compression only supported on Windows
        :raises ValueError: HDF5 is not installed
        :raises ValueError: HDF5 version is >1.8.xx
        """
        compression = compression.lower() if compression else None
        compression = None if compression == "none" else compression
        try:
            self._compression = BdvCompression(compression)
        except ValueError:
            raise ValueError(f"Invalid compression codec: {compression}. Must be one of {BdvCompression.__members__}")

    @property
    def batch_size_px(self) -> int:
        return CHUNK_SIZE_PX

    def configure(self, config: WriterConfig) -> None:
        super().configure(config)
        self._output_file = self.dir / f"{self.config.file_name}.n5"
        self._output_file = self._output_file.resolve()

        self._tiles_set.add(tuple(self.config.position_um))
        self._channels_set.add(self.config.channel_name)

        # self._channel_idx = self.metadata.channel_idx
        dict_key = (len(self._tiles_set), self.config.channel_idx)

        if dict_key in self._tile_shape_dict:
            raise ValueError(f"Duplicate tile/channel configuration: {dict_key}")

        self._tile_shape_dict[dict_key] = (
            self.config.frame_count,
            self.config.frame_shape.y,
            self.config.frame_shape.x,
        )

        self.config.voxel_size.y *= np.cos(self._theta_deg * np.pi / 180.0)

        # shearing based on theta and y/z pixel sizes
        shear = -np.tan(self._theta_deg * np.pi / 180.0) * self.config.voxel_size.y / self.config.voxel_size.z
        self._affine_deskew_dict[dict_key] = np.array(
            ([1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, shear, 1.0, 0.0])
        )

        scale_x = self.config.voxel_size.x / self.config.voxel_size.y
        scale_y = 1.0
        scale_z = self.config.voxel_size.z / self.config.voxel_size.y
        self._affine_scale_dict[dict_key] = np.array(
            ([scale_x, 0.0, 0.0, 0.0], [0.0, scale_y, 0.0, 0.0], [0.0, 0.0, scale_z, 0.0])
        )

        shift_x = scale_x * (self.config.position_um.x / self.config.voxel_size.x)
        shift_y = scale_y * (self.config.position_um.y / self.config.voxel_size.y)
        shift_z = scale_z * (self.config.position_um.z / self.config.voxel_size.z)
        self._affine_shift_dict[dict_key] = np.array(
            ([1.0, 0.0, 0.0, shift_x], [0.0, 1.0, 0.0, shift_y], [0.0, 0.0, 1.0, shift_z])
        )

    def _initialize(self) -> None:
        # compute necessary inputs to BDV/XML files
        # pyramid subsampling factors xyz
        # TODO CALCULATE THESE AS WITH ZARRV3 WRITER
        subsamp = (
            (1, 1, 1),
            (2, 2, 2),
            (4, 4, 4),
        )
        # chunksize xyz
        blockdim = (
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
            (4, 256, 256),
        )

        self._npy2bdv = npy2bdv.BdvWriter(
            filename=str(self._output_file),
            subsamp=subsamp,
            blockdim=blockdim,
            compression=self._compression,
            compression_opts=B3D_COMPRESSION_OPTS if self.compression == "b3d" else None,
            ntiles=len(self._tiles_set),
            nchannels=len(self._channels_set),
            overwrite=False,
        )

        # append all views based to bdv writer
        # this is necessary for bdv writer to have the metadata to write the xml at the end
        # if a view already exists in the bdv file, it will be skipped and not overwritten
        image_size_z = int(ceil(self.config.frame_count / CHUNK_SIZE_PX) * CHUNK_SIZE_PX)
        for key in self._tile_shape_dict:
            append_tile, append_channel = key
            self._npy2bdv.append_view(
                stack=None,
                virtual_stack_dim=(image_size_z, self.config.frame_shape.y, self.config.frame_shape.x),
                tile=append_tile,
                channel=append_channel,
                voxel_size_xyz=tuple(self.config.voxel_size),
                voxel_units="um",
            )

        self.log.info(f"Initialized. Writing to {self._output_file}")

    def _process_batch(self, batch_data) -> None:
        self._npy2bdv.append_substack(
            substack=batch_data,
            z_start=self.batch_count * self.batch_size_px,
            tile=self._tile_idx,
            channel=self.config.channel_idx,
        )

    def _finalize(self) -> None:
        self._npy2bdv.write_xml()

        for append_tile, append_channel in self._affine_deskew_dict:
            self._npy2bdv.append_affine(
                m_affine=self._affine_deskew_dict[(append_tile, append_channel)],
                name_affine="deskew",
                tile=append_tile,
                channel=append_channel,
            )

        for append_tile, append_channel in self._affine_scale_dict:
            self._npy2bdv.append_affine(
                m_affine=self._affine_scale_dict[(append_tile, append_channel)],
                name_affine="scale",
                tile=append_tile,
                channel=append_channel,
            )

        for append_tile, append_channel in self._affine_shift_dict:
            self._npy2bdv.append_affine(
                m_affine=self._affine_shift_dict[(append_tile, append_channel)],
                name_affine="shift",
                tile=append_tile,
                channel=append_channel,
            )
        self._npy2bdv.close()
        self._tile_idx += 1
        self.log.info(f"Finalized. Wrote {self.config.frame_count} frames to {self._output_file}")

from pathlib import Path

import numpy as np
import tifffile
from voxel.utils.log import VoxelLogging
from voxel_classic.devices.camera.base import BaseCamera


class BackgroundCollection:
    """Class for handling background collection for ExASPIM."""

    def __init__(self, path: str):
        """
        Initialize the BackgroundCollection object.

        :param path: Path to save the background images
        :type path: str
        """
        super().__init__()
        self.log = VoxelLogging.get_logger(object=self)
        self._path = Path(path)
        self._frame_count_px = 1
        self._filename = None
        self._acquisition_name = Path()
        self._data_type = np.dtype(np.uint16)

    @property
    def frame_count_px(self) -> int:
        """
        Get the frame count.

        :return: Frame count
        :rtype: int
        """
        return self._frame_count_px

    @frame_count_px.setter
    def frame_count_px(self, frame_count_px: int) -> None:
        """
        Set the frame count.

        :param frame_count_px: Frame count
        :type frame_count_px: int
        """
        self._frame_count_px = frame_count_px

    @property
    def data_type(self) -> np.dtype:
        """
        Get the data type.

        :return: Data type
        :rtype: np.dtype
        """
        return self._data_type

    @data_type.setter
    def data_type(self, data_type: np.dtype) -> None:
        """
        Set the data type.

        :param data_type: Data type
        :type data_type: np.dtype
        """
        self.log.info(f"setting data type to: {data_type}")
        self._data_type = data_type

    @property
    def path(self) -> Path:
        """
        Get the path.

        :return: Path
        :rtype: Path
        """
        return self._path

    @path.setter
    def path(self, path: str) -> None:
        """
        Set the path.

        :param path: Path
        :type path: str
        """
        self._path = Path(path)
        self.log.info(f"setting path to: {path}")

    @property
    def acquisition_name(self) -> Path:
        """
        Get the acquisition name.

        :return: Acquisition name
        :rtype: Path
        """
        return self._acquisition_name

    @acquisition_name.setter
    def acquisition_name(self, acquisition_name: str) -> None:
        """
        Set the acquisition name.

        :param acquisition_name: Acquisition name
        :type acquisition_name: str
        """
        self._acquisition_name = Path(acquisition_name)
        self.log.info(f"setting acquisition name to: {acquisition_name}")

    @property
    def filename(self) -> str | None:
        """
        Get the filename.

        :return: Filename
        :rtype: str
        """
        return self._filename

    @filename.setter
    def filename(self, filename: str) -> None:
        """
        Set the filename.

        :param filename: Filename
        :type filename: str
        """
        self._filename = (
            filename.replace(".tiff", "").replace(".tif", "")
            if filename.endswith(".tiff") or filename.endswith(".tif")
            else f"{filename}"
        )
        self.log.info(f"setting filename to: {filename}")

    def start(self, device: BaseCamera) -> None:
        """
        Start the background collection process.

        :param device: Camera device
        :type device: BaseCamera
        """
        camera = device
        trigger = camera.trigger
        trigger["mode"] = "off"
        camera.trigger = trigger
        # prepare and start camera
        camera.frame_number = 0
        camera.prepare()
        camera.start()
        background_stack = np.zeros(
            (self._frame_count_px, camera.image_height_px, camera.image_width_px),
            dtype=self._data_type,
        )
        for frame in range(self._frame_count_px):
            background_stack[frame] = camera.grab_frame()
            camera.acquisition_state()
        # close writer and camera
        camera.stop()
        # reset the trigger
        trigger["mode"] = "on"
        camera.trigger = trigger
        # average and save the image
        background_image = np.mean(background_stack, axis=0)
        tifffile.imwrite(
            Path(self.path, self._acquisition_name, f"{self.filename}.tiff"), background_image.astype(self._data_type)
        )

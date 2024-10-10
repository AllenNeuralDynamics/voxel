import logging
import numpy as np
import tifffile
from pathlib import Path
from voxel.devices.camera.base import BaseCamera


class BackgroundCollection:

    def __init__(self, path: str):

        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._path = Path(path)
        self._frame_count_px_px = 1
        self._filename = None
        self._acquisition_name = Path()
        self._data_type = None

    @property
    def frame_count_px(self):
        return self._frame_count_px_px

    @frame_count_px.setter
    def frame_count_px(self, frame_count_px: int):
        self._frame_count_px_px = frame_count_px

    @property
    def data_type(self):
        return self._data_type

    @data_type.setter
    def data_type(self, data_type: np.unsignedinteger):
        self.log.info(f'setting data type to: {data_type}')
        self._data_type = data_type

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path: str):
        self._path = Path(path)
        self.log.info(f'setting path to: {path}')

    @property
    def acquisition_name(self):
        return self._acquisition_name

    @acquisition_name.setter
    def acquisition_name(self, acquisition_name: str):
        self._acquisition_name = Path(acquisition_name)
        self.log.info(f'setting acquisition name to: {acquisition_name}')
        
    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, filename: str):
        self._filename = filename.replace(".tiff","").replace(".tif", "") \
            if filename.endswith(".tiff") or filename.endswith(".tif") else f"{filename}"
        self.log.info(f'setting filename to: {filename}')

    def start(self, device: BaseCamera):
        camera = device
        # store initial trigger mode
        trigger_dict = camera.trigger
        # turn trigger off
        trigger_dict['mode'] = 'off'
        camera.trigger = trigger_dict
        # prepare and start camera
        camera.prepare()
        camera.start()
        background_stack = np.zeros((self._frame_count_px_px, camera.height_px // camera.binning, camera.width_px // camera.binning), dtype=self._data_type)
        for frame in range(self._frame_count_px_px):
            background_stack[frame] = camera.grab_frame()
        # close writer and camera
        camera.stop()
        # reset the trigger
        trigger_dict['mode'] = 'on'
        camera.trigger = trigger_dict
        # average and save the image
        background_image = np.median(background_stack, axis=0)
        tifffile.imwrite(Path(self.path, self._acquisition_name, f"{self.filename}.tiff"), background_image.astype(self._data_type))
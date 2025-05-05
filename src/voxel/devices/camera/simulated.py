import logging
import time
import multiprocessing
from multiprocessing import Event, Process, Queue, Value
from typing import Dict, Any

import numpy

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.camera.base import BaseCamera
from voxel.processes.downsample.gpu.gputools.downsample_2d import GPUToolsDownSample2D

BUFFER_SIZE_FRAMES = 8
MIN_WIDTH_PX = 64
MAX_WIDTH_PX = 14192
DIVISIBLE_WIDTH_PX = 16
MIN_HEIGHT_PX = 2
MAX_HEIGHT_PX = 10640
DIVISIBLE_HEIGHT_PX = 1
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 6e4

BINNINGS = {1: 1, 2: 2, 4: 4}

PIXEL_TYPES = {"mono8": "uint8", "mono16": "uint16"}

LINE_INTERVALS_US = {"mono8": 500.00, "mono16": 500.0}

MODES = {
    "on": "On",
    "off": "Off",
}

SOURCES = {
    "internal": "None",
    "external": "Line0",
}

POLARITIES = {
    "rising": "RisingEdge",
    "falling": "FallingEdge",
}


class SimulatedCamera(BaseCamera):
    """Camera class for simulating camera operations.

    :param BaseCamera: Base class for camera
    :type BaseCamera: BaseCamera
    :raises ValueError: If invalid trigger mode, source, or polarity is set
    :return: Camera instance
    :rtype: Camera
    """

    def __init__(self, id: str) -> None:
        """Initialize the Camera instance.

        :param id: Identifier for the camera
        :type id: str
        """
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = id
        self.terminate_frame_grab = Event()
        self.terminate_frame_grab.clear()
        self._pixel_type = "mono16"
        self._line_interval_us = LINE_INTERVALS_US[self._pixel_type]
        self._exposure_time_ms = 10
        self._width_px = MAX_WIDTH_PX
        self._height_px = MAX_HEIGHT_PX
        self._width_offset_px = 0
        self._height_offset_px = 0
        self._binning = 1
        self._trigger = {"mode": "on", "source": "internal", "polarity": "rising"}

    @DeliminatedProperty(minimum=MIN_EXPOSURE_TIME_MS, maximum=MAX_EXPOSURE_TIME_MS, step=0.001)
    def exposure_time_ms(self) -> float:
        """Get the exposure time in milliseconds.

        :return: Exposure time in milliseconds
        :rtype: float
        """
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time in milliseconds.

        :param exposure_time_ms: Exposure time in milliseconds
        :type exposure_time_ms: float
        """
        if exposure_time_ms < MIN_EXPOSURE_TIME_MS or exposure_time_ms > MAX_EXPOSURE_TIME_MS:
            self.log.warning(
                f"exposure time must be >{MIN_EXPOSURE_TIME_MS} ms \
                             and <{MAX_EXPOSURE_TIME_MS} ms. Setting exposure time to {MAX_EXPOSURE_TIME_MS} ms"
            )

        # Note: round ms to nearest us
        self._exposure_time_ms = exposure_time_ms
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")

    @DeliminatedProperty(minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX, step=DIVISIBLE_WIDTH_PX)
    def width_px(self) -> int:
        """Get the width in pixels.

        :return: Width in pixels
        :rtype: int
        """
        return self._width_px

    @width_px.setter
    def width_px(self, value: int) -> None:
        """Set the width in pixels.

        :param value: Width in pixels
        :type value: int
        """
        self._width_px = value
        self.log.info(f"width set to: {value} px")

    @DeliminatedProperty(minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX, step=DIVISIBLE_WIDTH_PX)
    def width_offset_px(self) -> int:
        """Get the width offset in pixels.

        :return: Width offset in pixels
        :rtype: int
        """
        return self._width_offset_px

    @width_offset_px.setter
    def width_offset_px(self, value: int) -> None:
        """Set the width offset in pixels.

        :param value: Width offset in pixels
        :type value: int
        """
        if value + self._width_px > MAX_WIDTH_PX:
            value = MAX_WIDTH_PX - self._width_px
            self.log.warning(f"width offset and width must not exceed {MAX_WIDTH_PX} px. Setting offset to {value} px")

        self._width_offset_px = value
        self.log.info(f"width offset set to: {value} px")

    @DeliminatedProperty(minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX, step=DIVISIBLE_HEIGHT_PX)
    def height_px(self) -> int:
        """Get the height in pixels.

        :return: Height in pixels
        :rtype: int
        """
        return self._height_px

    @height_px.setter
    def height_px(self, value: int) -> None:
        """Set the height in pixels.

        :param value: Height in pixels
        :type value: int
        """
        self._height_px = value
        self.log.info(f"height set to: {value} px")

    @DeliminatedProperty(minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX, step=DIVISIBLE_HEIGHT_PX)
    def height_offset_px(self) -> int:
        """Get the height offset in pixels.

        :return: Height offset in pixels
        :rtype: int
        """
        return self._height_offset_px

    @height_offset_px.setter
    def height_offset_px(self, value: int) -> None:
        """Set the height offset in pixels.

        :param value: Height offset in pixels
        :type value: int
        """
        if value + self._height_px > MAX_HEIGHT_PX:
            value = MAX_HEIGHT_PX - self._height_px
            self.log.warning(
                f"height offset and height must not exceed {MAX_HEIGHT_PX} px. Setting offset to {value} px"
            )

        self._height_offset_px = value
        self.log.info(f"height offset set to: {value} px")

    @property
    def trigger(self) -> Dict[str, str]:
        """Get the trigger settings.

        :return: Trigger settings
        :rtype: dict
        """
        return self._trigger

    @trigger.setter
    def trigger(self, trigger: Dict[str, str]) -> None:
        """Set the trigger settings.

        :param trigger: Trigger settings
        :type trigger: dict
        :raises ValueError: If invalid trigger mode, source, or polarity is set
        """
        mode = trigger["mode"]
        source = trigger["source"]
        polarity = trigger["polarity"]

        valid_mode = list(MODES.keys())
        if mode not in valid_mode:
            raise ValueError("mode must be one of %r." % valid_mode)
        valid_source = list(SOURCES.keys())
        if source not in valid_source:
            raise ValueError("source must be one of %r." % valid_source)
        valid_polarity = list(POLARITIES.keys())
        if polarity not in valid_polarity:
            raise ValueError("polarity must be one of %r." % valid_polarity)
        self._trigger = dict(trigger)

    @property
    def binning(self) -> int:
        """Get the binning value.

        :return: Binning value
        :rtype: int
        """
        return self._binning

    @binning.setter
    def binning(self, binning: int) -> None:
        """Set the binning value.

        :param binning: Binning value
        :type binning: int
        :raises ValueError: If invalid binning value is set
        """
        valid_binning = list(BINNINGS.keys())
        if binning not in valid_binning:
            raise ValueError("binning must be one of %r." % BINNINGS)
        else:
            self._binning = BINNINGS[binning]
            # initialize the downsampling in 2d
            self.gpu_binning = GPUToolsDownSample2D(binning=self._binning, mode="average")

    @property
    def pixel_type(self) -> str:
        """Get the pixel type.

        :return: Pixel type
        :rtype: str
        """
        # invert the dictionary and find the abstracted key to output
        return self._pixel_type

    @pixel_type.setter
    def pixel_type(self, pixel_type: str) -> None:
        """Set the pixel type.

        :param pixel_type: Pixel type
        :type pixel_type: str
        :raises ValueError: If invalid pixel type is set
        """
        valid = list(PIXEL_TYPES.keys())
        if pixel_type not in valid:
            raise ValueError("pixel_type must be one of %r." % valid)

        self._pixel_type = pixel_type
        self._line_interval_us = LINE_INTERVALS_US[pixel_type]
        self.log.info(f"pixel type set_to: {pixel_type}")

    @property
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds.

        :return: Line interval in microseconds
        :rtype: float
        """
        return self._line_interval_us

    @property
    def sensor_width_px(self) -> int:
        """Get the sensor width in pixels.

        :return: Sensor width in pixels
        :rtype: int
        """
        return MAX_WIDTH_PX

    @property
    def sensor_height_px(self) -> int:
        """Get the sensor height in pixels.

        :return: Sensor height in pixels
        :rtype: int
        """
        return MAX_HEIGHT_PX

    @property
    def frame_time_ms(self) -> float:
        """Get the frame time in milliseconds.

        :return: Frame time in milliseconds
        :rtype: float
        """
        return self._height_px * self._line_interval_us / 1000 + self._exposure_time_ms

    def prepare(self, frame_count=float("inf")) -> None:
        """Prepare the camera for capturing frames.

        :param frame_count: Number of frames to capture
        :type frame_count: int
        """
        self.log.info("simulated camera preparing...")

    @property
    def mainboard_temperature_c(self) -> float:
        """
        Get the mainboard temperature in Celsius.

        :return: The mainboard temperature in Celsius.
        :rtype: float
        """
        return 40.0 + numpy.random.randn()

    @property
    def sensor_temperature_c(self) -> float:
        """
        Get the sensor temperature in Celsius.

        :return: The sensor temperature in Celsius.
        :rtype: float
        """
        return 4.0 + numpy.random.randn()

    @property
    def readout_mode(self) -> str:
        """
        Get the readout mode.

        :return: The readout mode.
        :rtype: str
        """
        return "rolling shutter"

    def start(self, frames=float("inf")) -> None:
        """Start camera."""
        self.log.info("simulated camera starting...")

    def stop(self) -> None:
        """Stop camera,."""
        self.log.info("simulated camera stopping...")

    def abort(self) -> None:
        """Abort camera."""
        self.log.info("simulated camera stopping...")
        self.stop()

    def reset(self) -> None:
        """Reset camera."""
        self.log.info("simulated camera resetting...")
        pass

    def close(self) -> None:
        """Close camera."""
        self.log.info("simulated camera closing...")
        pass

    def grab_frame(self) -> numpy.ndarray:
        """Grab the latest frame.

        :return: Latest frame
        :rtype: numpy.ndarray
        """
        image = numpy.random.randint(
            low=128, high=256, size=(self.image_height_px, self.image_width_px), dtype=PIXEL_TYPES[self._pixel_type]
        )
        self._latest_frame = numpy.copy(image)
        self.frame_number += 1
        if self._binning > 1:
            return self.gpu_binning.run(image)
        else:
            return image

    @property
    def latest_frame(self) -> numpy.ndarray:
        """Get the latest frame.

        :return: Latest frame
        :rtype: numpy.ndarray
        """
        # return latest frame from internal queue buffer
        return self._latest_frame

    def acquisition_state(self) -> Dict[str, Any]:
        """Return the acquisition state of the camera.

        :return: Acquisition state
        :rtype: dict
        """

        state = {}
        state["Frame Index"] = self.frame_number
        state["Input Buffer Size"] = 0
        state["Output Buffer Size"] = BUFFER_SIZE_FRAMES
        # number of underrun, i.e. dropped frames
        state["Dropped Frames"] = 0
        state["Data Rate [MB/s]"] = (
            1.0 / (self.frame_time_ms / 1000)
            * self._width_px
            * self._height_px
            * numpy.dtype(self._pixel_type).itemsize
            / self._binning**2
            / 1024**2
        )
        state["Frame Rate [fps]"] = 1.0 / (self.frame_time_ms / 1000)
        self.log.info(
            f"id: {self.id}, "
            f"frame: {state['Frame Index']}, "
            f"input: {state['Input Buffer Size']}, "
            f"output: {state['Output Buffer Size']}, "
            f"dropped: {state['Dropped Frames']}, "
            f"data rate: {state['Data Rate [MB/s]']:.2f} [MB/s], "
            f"frame rate: {state['Frame Rate [fps]']:.2f} [fps]."
        )
        return state

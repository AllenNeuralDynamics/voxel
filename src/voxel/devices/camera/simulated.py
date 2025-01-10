import logging
import time
import multiprocessing
from multiprocessing import Event, Process, Queue, Value

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

LINE_INTERVALS_US = {"mono8": 10.00, "mono16": 45.44}

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


class Camera(BaseCamera):

    width_px = DeliminatedProperty(
        fget=lambda instance: getattr(instance, "_width_px"),
        fset=lambda instance, value: setattr(instance, "_width_px", value),
        minimum=MIN_WIDTH_PX,
        maximum=MAX_WIDTH_PX,
        step=DIVISIBLE_WIDTH_PX,
    )
    width_offset_px = DeliminatedProperty(
        fget=lambda instance: getattr(instance, "_width_offset_px"),
        fset=lambda instance, value: setattr(instance, "_width_offset_px", value),
        minimum=MIN_WIDTH_PX,
        maximum=MAX_WIDTH_PX,
        step=DIVISIBLE_WIDTH_PX,
    )
    height_px = DeliminatedProperty(
        fget=lambda instance: getattr(instance, "_height_px"),
        fset=lambda instance, value: setattr(instance, "_height_px", value),
        minimum=MIN_HEIGHT_PX,
        maximum=MAX_HEIGHT_PX,
        step=DIVISIBLE_HEIGHT_PX,
    )
    height_offset_px = DeliminatedProperty(
        fget=lambda instance: getattr(instance, "_height_offset_px"),
        fset=lambda instance, value: setattr(instance, "_height_offset_px", value),
        minimum=MIN_HEIGHT_PX,
        maximum=MAX_HEIGHT_PX,
        step=DIVISIBLE_HEIGHT_PX,
    )

    def __init__(self, id):

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
        
        self._frame = Value("i", 0)
        self._frame_rate = Value("d", 0.0)
        self._dropped_frames = Value("d", 0.0)
        self._buffer = Queue()

    @DeliminatedProperty(minimum=MIN_EXPOSURE_TIME_MS, maximum=MAX_EXPOSURE_TIME_MS, step=0.001)
    def exposure_time_ms(self):
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):

        if exposure_time_ms < MIN_EXPOSURE_TIME_MS or exposure_time_ms > MAX_EXPOSURE_TIME_MS:
            self.log.warning(
                f"exposure time must be >{MIN_EXPOSURE_TIME_MS} ms \
                             and <{MAX_EXPOSURE_TIME_MS} ms. Setting exposure time to {MAX_EXPOSURE_TIME_MS} ms"
            )

        # Note: round ms to nearest us
        self._exposure_time_ms = exposure_time_ms
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")

    @DeliminatedProperty(minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX, step=DIVISIBLE_WIDTH_PX)
    def width_px(self):
        return self._width_px

    @width_px.setter
    def width_px(self, value: int):

        self._width_px = value
        self.log.info(f"width set to: {value} px")

    @DeliminatedProperty(minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX, step=DIVISIBLE_WIDTH_PX)
    def width_offset_px(self):
        return self._width_offset_px

    @width_offset_px.setter
    def width_offset_px(self, value: int):

        if value + self._width_px > MAX_WIDTH_PX:
            value = MAX_WIDTH_PX - self._width_px
            self.log.warning(f"width offset and width must not exceed {MAX_WIDTH_PX} px. Setting offset to {value} px")

        self._width_offset_px = value
        self.log.info(f"width offset set to: {value} px")

    @DeliminatedProperty(minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX, step=DIVISIBLE_HEIGHT_PX)
    def height_px(self):
        return self._height_px

    @height_px.setter
    def height_px(self, value: int):

        # Note: round ms to nearest us
        self._height_px = value
        self.log.info(f"height set to: {value} px")

    @DeliminatedProperty(minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX, step=DIVISIBLE_HEIGHT_PX)
    def height_offset_px(self):
        return self._height_offset_px

    @height_offset_px.setter
    def height_offset_px(self, value: int):

        if value + self._height_px > MAX_HEIGHT_PX:
            value = MAX_HEIGHT_PX - self._height_px
            self.log.warning(
                f"height offset and height must not exceed {MAX_HEIGHT_PX} px. Setting offset to {value} px"
            )

        self._height_offset_px = value
        self.log.info(f"height offset set to: {value} px")

    @property
    def trigger(self):
        return self._trigger

    @trigger.setter
    def trigger(self, trigger: dict):

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
    def binning(self):
        return self._binning

    @binning.setter
    def binning(self, binning: int):
        valid_binning = list(BINNINGS.keys())
        if binning not in valid_binning:
            raise ValueError("binning must be one of %r." % BINNINGS)
        else:
            self._binning = BINNINGS[binning]
            # initialize the downsampling in 2d
            self.gpu_binning = GPUToolsDownSample2D(binning=self._binning)

    @property
    def pixel_type(self):
        pixel_type = self._pixel_type
        # invert the dictionary and find the abstracted key to output
        return next(key for key, value in PIXEL_TYPES.items() if value == pixel_type)

    @pixel_type.setter
    def pixel_type(self, pixel_type_bits: str):
        valid = list(PIXEL_TYPES.keys())
        if pixel_type_bits not in valid:
            raise ValueError("pixel_type_bits must be one of %r." % valid)

        self._pixel_type = PIXEL_TYPES[pixel_type_bits]
        self._line_interval_us = LINE_INTERVALS_US[pixel_type_bits]
        self.log.info(f"pixel type set_to: {pixel_type_bits}")

    @property
    def line_interval_us(self):
        return self._line_interval_us

    @property
    def sensor_width_px(self):
        return MAX_WIDTH_PX

    @property
    def sensor_height_px(self):
        return MAX_HEIGHT_PX

    @property
    def frame_time_ms(self):
        return self._height_px * self._line_interval_us / 1000 + self._exposure_time_ms

    def prepare(self, frame_count: int):
        self.log.info("simulated camera preparing...")
        self._frame_generator = FrameGenerator()
        self._frame_generator.prepare(
            frame_count,
            self._width_px,
            self._height_px,
            self._pixel_type,
            self.frame_time_ms
        )

    def start(self):
        self._frame_generator.start()

    def stop(self):
        self.log.info("simulated camera stopping...")
        self._frame_generator.stop()

    def grab_frame(self):
        image = self._frame_generator.get_latest_frame()
        if self._binning > 1:
            return self.gpu_binning.run(image)
        else:
            return image

    @property
    def latest_frame(self):
        # return latest frame from internal queue buffer
        return self._latest_frame

    def signal_acquisition_state(self):
        # copy into new variables for async
        frame_rate_async = self._frame_generator.frame_rate
        dropped_frames_async = self._frame_generator.dropped_frames
        input_buffer_size = self._frame_generator._buffer.qsize()

        state = {}
        state['Frame Index'] = self._frame_generator.frame
        state['Input Buffer Size'] = input_buffer_size
        state['Output Buffer Size'] = BUFFER_SIZE_FRAMES - input_buffer_size
         # number of underrun, i.e. dropped frames
        state['Dropped Frames'] = dropped_frames_async
        state['Data Rate [MB/s]'] = frame_rate_async*self._width_px*self._height_px*numpy.dtype(self._pixel_type).itemsize/self._binning**2/1e6
        state['Frame Rate [fps]'] = frame_rate_async
        self.log.info(f"id: {self.id}, "
                      f"frame: {state['Frame Index']}, "
                      f"input: {state['Input Buffer Size']}, "
                      f"output: {state['Output Buffer Size']}, "
                      f"dropped: {state['Dropped Frames']}, "
                      f"data rate: {state['Data Rate [MB/s]']:.2f} [MB/s], "
                      f"frame rate: {state['Frame Rate [fps]']:.2f} [fps].")
        return state

class FrameGenerator():
    # frame generator into separate class due to voxel wrapping and thread locking of device classes
    def __init__(self):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # multiprocessing shared values
        self._frame = Value("i", 0)
        self._frame_rate = Value("d", 0.0)
        self._dropped_frames = Value("d", 0.0)
        self._buffer = Queue()

    @property
    def frame(self):
        # current frame index
        return self._frame.value
    
    @property
    def frame_rate(self):
        # estimated frame rate
        return self._frame_rate.value

    @property
    def dropped_frames(self):
        # logged dropped frames
        return self._dropped_frames.value
    
    def get_latest_frame(self):
        # return latest frame from buffer
        while self._buffer.empty():
            time.sleep(0.01)
        image = self._buffer.get()
        return image

    def prepare(self,
                frame_count,
                width_px,
                height_px,
                pixel_type,
                frame_time_ms):
        # prepare the frame generator process
        self._process = Process(
            target=self._run,
            args=(
                frame_count,
                width_px,
                height_px,
                frame_time_ms,
                pixel_type,
                self._buffer,
                self._frame,
                self._frame_rate,
                self._dropped_frames,
            ),
        )

    def start(self):
        # start the frame generator process
        self._process.start()

    def stop(self):
        # stop the frame generator process
        self._process.join()

    def _run(self,
            frame_count: int,
            width_px: int,
            height_px: int,
            frame_time_ms: float,
            pixel_type: str,
            buffer: multiprocessing.Queue,
            frame: multiprocessing.Value,
            frame_rate: multiprocessing.Value,
            dropped_frames: multiprocessing.Value):
        # frame generator process
        i = 1
        frame_count = frame_count if frame_count is not None else 1
        while i <= frame_count:
            start_time = time.time()
            image = numpy.random.randint(low=128, high=256, size=(height_px, width_px), dtype=pixel_type)
            while (time.time() - start_time) < frame_time_ms / 1000:
                time.sleep(0.01)
            # add frame to buffer or log a dropped frame if buffer is full
            if buffer.qsize() < BUFFER_SIZE_FRAMES:
                buffer.put(image)
            else:
                dropped_frames.value += 1
                self.log.warning('buffer full, frame dropped.')
            frame.value += 1
            # handle infinite streaming from frame generator process
            i = i if frame_count is None else i+1
            end_time = time.time()
            # estimate frame rate
            frame_rate.value = 1/(end_time - start_time)

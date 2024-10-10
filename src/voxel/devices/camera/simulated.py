import logging
import numpy
import time
from multiprocessing import Process, Queue, Event
from voxel.devices.camera.base import BaseCamera
from voxel.processes.downsample.gpu.gputools.downsample_2d import GPUToolsDownSample2D
from voxel.descriptors.deliminated_property import DeliminatedProperty
from threading import Thread

BUFFER_SIZE_FRAMES = 8
MIN_WIDTH_PX = 64
MAX_WIDTH_PX = 14192
DIVISIBLE_WIDTH_PX = 16
MIN_HEIGHT_PX = 2
MAX_HEIGHT_PX = 10640
DIVISIBLE_HEIGHT_PX = 1
MIN_EXPOSURE_TIME_MS = 0.001
MAX_EXPOSURE_TIME_MS = 6e4


BINNING = {
    1: 1,
    2: 2,
    4: 4
}

PIXEL_TYPES = {
    "mono8": "uint8",
    "mono16": "uint16"
}

LINE_INTERVALS_US = {
    "mono8": 10.00,
    "mono16": 20.00
}

MODES= {
        "on": "On",
        "off": "Off",
    }
SOURCES= {
        "internal": "None",
        "external": "Line0",
    }
POLARITIES =  {
        "rising": "RisingEdge",
        "falling": "FallingEdge",
    }

class Camera(BaseCamera):

    width_px = DeliminatedProperty(fget=lambda instance: getattr(instance, '_width_px'),
                                   fset=lambda instance, value: setattr(instance, '_width_px', value),
                                   minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX,
                                   step=DIVISIBLE_WIDTH_PX)
    width_offset_px = DeliminatedProperty(fget=lambda instance: getattr(instance, '_width_offset_px'),
                                   fset=lambda instance, value: setattr(instance, '_width_offset_px', value),
                                   minimum=MIN_WIDTH_PX, maximum=MAX_WIDTH_PX,
                                   step=DIVISIBLE_WIDTH_PX)
    height_px = DeliminatedProperty(fget=lambda instance: getattr(instance, '_height_px'),
                                   fset=lambda instance, value: setattr(instance, '_height_px', value),
                                   minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX,
                                   step=DIVISIBLE_HEIGHT_PX)
    height_offset_px = DeliminatedProperty(fget=lambda instance: getattr(instance, '_height_offset_px'),
                                    fset=lambda instance, value: setattr(instance, '_height_offset_px', value),
                                    minimum=MIN_HEIGHT_PX, maximum=MAX_HEIGHT_PX,
                                    step=DIVISIBLE_HEIGHT_PX)



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
        self._trigger = {'mode': 'on',
                         'source': 'internal',
                         'polarity': 'rising'}
        self._latest_frame = None

    @DeliminatedProperty(minimum=MIN_EXPOSURE_TIME_MS, maximum=MAX_EXPOSURE_TIME_MS, step=0.001)
    def exposure_time_ms(self):
        return self._exposure_time_ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):

        if exposure_time_ms < MIN_EXPOSURE_TIME_MS or \
                exposure_time_ms > MAX_EXPOSURE_TIME_MS:
            self.log.warning(f"exposure time must be >{MIN_EXPOSURE_TIME_MS} ms \
                             and <{MAX_EXPOSURE_TIME_MS} ms. Setting exposure time to {MAX_EXPOSURE_TIME_MS} ms")

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
            self.log.warning(f"height offset and height must not exceed {MAX_HEIGHT_PX} px. Setting offset to {value} px")

        self._height_offset_px = value
        self.log.info(f"height offset set to: {value} px")

    @property
    def trigger(self):
        return self._trigger

    @trigger.setter
    def trigger(self, trigger: dict):

        mode = trigger['mode']
        source = trigger['source']
        polarity = trigger['polarity']

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
        valid_binning = list(BINNING.keys())
        if binning not in valid_binning:
            raise ValueError("binning must be one of %r." % BINNING)
        else:
            self._binning = BINNING[binning]
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

    def prepare(self):
        self.log.info('simulated camera preparing...')


    def start(self, frame_count: int = float('inf')):
        self.log.info('simulated camera starting...')
        self.frame = 0


    def stop(self):
        self.log.info('simulated camera stopping...')
        self.frame = 0

    def grab_frame(self):

        self.frame += 1
        image = numpy.random.randint(low=128, high=256, size=(self._height_px, self._width_px), dtype=self._pixel_type)
        self._latest_frame = image
        if self._binning > 1:
            return self.gpu_binning.run(image)
        else:
            return image

    @property
    def latest_frame(self):
        return self._latest_frame

    # def signal_acquisition_state(self):
    #     """return a dict with the state of the acquisition buffers"""
    #     state = {}
    #     state['Frame Index'] = self.frame
    #     state['Input Buffer Size'] = len(self.buffer)
    #     state['Output Buffer Size'] = BUFFER_SIZE_FRAMES - len(self.buffer)
    #     # number of underrun, i.e. dropped frames
    #     state['Dropped Frames'] = self.dropped_frames
    #     state['Data Rate [MB/s]'] = self.frame_rate * self._width_px * self._height_px * numpy.dtype(
    #         self._pixel_type).itemsize / self._binning ** 2 / 1e6
    #     state['Frame Rate [fps]'] = self.frame_rate
    #     self.log.info(f"id: {self.id}, "
    #                   f"frame: {state['Frame Index']}, "
    #                   f"input: {state['Input Buffer Size']}, "
    #                   f"output: {state['Output Buffer Size']}, "
    #                   f"dropped: {state['Dropped Frames']}, "
    #                   f"data rate: {state['Data Rate [MB/s]']:.2f} [MB/s], "
    #                   f"frame rate: {state['Frame Rate [fps]']:.2f} [fps].")
    #     return state

    def abort(self):
        pass

    def close(self):
        pass

import ctypes as ct
import logging

import numpy
import numpy as np
from egrabber import (
    BUFFER_INFO_BASE,
    GENTL_INFINITE,
    INFO_DATATYPE_PTR,
    INFO_DATATYPE_SIZET,
    STREAM_INFO_NUM_AWAIT_DELIVERY,
    STREAM_INFO_NUM_DELIVERED,
    STREAM_INFO_NUM_QUEUED,
    STREAM_INFO_NUM_UNDERRUN,
    Buffer,
    EGenTL,
    EGrabber,
    EGrabberDiscovery,
    query,
)

from voxel.descriptors.deliminated_property import DeliminatedProperty
from voxel.devices.camera.base import BaseCamera
from voxel.devices.utils.singleton import thread_safe_singleton
from voxel.processes.downsample.gpu.gputools.downsample_2d import GPUToolsDownSample2D

# from copy import deepcopy

BUFFER_SIZE_MB = 2400

# generate valid binning by querying egrabber
# should be of the form
# {"2": "X2",
#  "3": "X3",
#  "4": "X4"...
# }
BINNINGS = dict()

# generate valid pixel types by querying egrabber
# should be of the form
# {"mono8": "Mono8",
#  "mono12": "Mono12",
#  "mono16": "Mono16"...
# }
PIXEL_TYPES = dict()

# generate line intervals by querying egrabber
# should be of the form
# {"mono8": 15.0,
#  "mono12": 25.5,
#  "mono16": 45.44 ...
# }
LINE_INTERVALS_US = dict()

# generate bit packing modes by querying egrabber
# should be of the form
# {"msb": "Msb",
#  "lsb": "Lsb",
#  "none": "None" ...
# }
BIT_PACKING_MODES = dict()

# generate triggers by querying egrabber
# should be of the form
# {"mode": {"on": "On",
#           "off": "Off"},
#  "source": {"software": "Software",
#             "line0": "Line0"},
#  "polarity": {"risingedge": "RisingEdge",
#               "fallingedge": "FallingEdge"}
# }
MODES = dict()
SOURCES = dict()
POLARITIES = dict()


@thread_safe_singleton
def get_egentl_singleton() -> EGenTL:
    return EGenTL()


class Camera(BaseCamera):

    def __init__(self, id: str) -> None:
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.id = str(id)  # convert to string incase serial # is entered as int
        self.gentl = get_egentl_singleton()
        self._latest_frame = None

        discovery = EGrabberDiscovery(self.gentl)
        discovery.discover()
        # list all possible grabbers
        egrabber_list = {"grabbers": []}
        interface_count = discovery.interface_count()
        for interfaceIndex in range(interface_count):
            device_count = discovery.device_count(interfaceIndex)
            for deviceIndex in range(device_count):
                if discovery.device_info(interfaceIndex, deviceIndex).deviceVendorName != "":
                    stream_count = discovery.stream_count(interfaceIndex, deviceIndex)
                    for streamIndex in range(stream_count):
                        info = {"interface": interfaceIndex, "device": deviceIndex, "stream": streamIndex}
                        egrabber_list["grabbers"].append(info)

        # for camera in discovery.cameras:
        del discovery

        # identify by serial number and return correct grabber
        if not egrabber_list["grabbers"]:
            raise ValueError("no valid cameras found. check connections and close any software.")

        try:
            for egrabber in egrabber_list["grabbers"]:
                grabber = EGrabber(
                    self.gentl, egrabber["interface"], egrabber["device"], egrabber["stream"], remote_required=True
                )
                # note the framegrabber serial number is also available through:
                # grabber.interface.get('DeviceSerialNumber)
                if grabber.remote.get("DeviceSerialNumber") == self.id:
                    self.log.info(f"grabber found for S/N: {self.id}")
                    self.grabber = grabber
                    self.egrabber = egrabber
                    break
        except:
            self.log.error(f"no grabber found for S/N: {self.id}")
            raise ValueError(f"no grabber found for S/N: {self.id}")

        del grabber
        # IMPORTANT: call stop here in the event that the camera previously crashed
        # if not called, the camera may not respond via the SDK
        self.grabber.remote.execute("AcquisitionStop")
        # initialize binning as 1
        self._binning = 1
        # initialize parameter values
        self._update_parameters()

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def exposure_time_ms(self):
        # us to ms conversion
        return self.grabber.remote.get("ExposureTime") / 1000

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float):
        # Note: round ms to nearest us
        self.grabber.remote.set("ExposureTime", round(exposure_time_ms * 1e3, 1))
        self.log.info(f"exposure time set to: {exposure_time_ms} ms")
        # refresh parameter values
        self._get_min_max_step_values()

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def width_px(self):
        return self.grabber.remote.get("Width")

    @width_px.setter
    def width_px(self, value: int):
        # reset offset to (0,0)
        self.grabber.remote.set("OffsetX", 0)
        self.grabber.remote.set("Width", value)
        centered_offset_px = round((self.max_width_px / 2 - value / 2) / self.step_width_px) * self.step_width_px
        self.grabber.remote.set("OffsetX", centered_offset_px)
        self.log.info(f"width set to: {value} px")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def width_offset_px(self):
        return self.grabber.remote.get("OffsetX")

    @DeliminatedProperty(minimum=float("-inf"), maximum=float("inf"))
    def height_px(self):
        return self.grabber.remote.get("Height")

    @height_px.setter
    def height_px(self, value: int):
        # reset offset to (0,0)
        self.grabber.remote.set("OffsetY", 0)
        self.grabber.remote.set("Height", value)
        centered_offset_px = round((self.max_height_px / 2 - value / 2) / self.step_height_px) * self.step_height_px
        self.grabber.remote.set("OffsetY", centered_offset_px)
        self.grabber.remote.set("Height", value)
        self.log.info(f"height set to: {value} px")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def height_offset_px(self):
        return self.grabber.remote.get("OffsetY")

    @property
    def pixel_type(self):
        pixel_type = self.grabber.remote.get("PixelFormat")
        # invert the dictionary and find the abstracted key to output
        return next(key for key, value in PIXEL_TYPES.items() if value == pixel_type)

    @pixel_type.setter
    def pixel_type(self, pixel_type_bits: str):
        valid = list(PIXEL_TYPES.keys())
        if pixel_type_bits not in valid:
            raise ValueError("pixel_type_bits must be one of %r." % valid)
        # note: for the Vieworks VP-151MX camera, the pixel type also controls line interval
        self.grabber.remote.set("PixelFormat", PIXEL_TYPES[pixel_type_bits])
        self.log.info(f"pixel type set to: {pixel_type_bits}")
        # refresh parameter values
        self._update_parameters()

    @property
    def bit_packing_mode(self):
        bit_packing = self.grabber.stream.get("UnpackingMode")
        # invert the dictionary and find the abstracted key to output
        return next(key for key, value in BIT_PACKING_MODES.items() if value == bit_packing)

    @bit_packing_mode.setter
    def bit_packing_mode(self, bit_packing: str):
        valid = list(BIT_PACKING_MODES.keys())
        if bit_packing not in valid:
            raise ValueError("bit_packing_mode must be one of %r." % valid)
        self.grabber.stream.set("UnpackingMode", BIT_PACKING_MODES[bit_packing])
        self.log.info(f"bit packing mode set to: {bit_packing}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def line_interval_us(self):
        pixel_type = self.pixel_type
        return LINE_INTERVALS_US[pixel_type]

    @property
    def frame_time_ms(self):
        return (self.line_interval_us * self.height_px) / 1000 + self.exposure_time_ms

    @property
    def trigger(self):
        mode = self.grabber.remote.get("TriggerMode")
        source = self.grabber.remote.get("TriggerSource")
        polarity = self.grabber.remote.get("TriggerActivation")
        return {
            "mode": next(key for key, value in MODES.items() if value == mode),
            "source": next(key for key, value in SOURCES.items() if value == source),
            "polarity": next(key for key, value in POLARITIES.items() if value == polarity),
        }

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
        # note: Setting TriggerMode if it's already correct will throw an error
        if self.grabber.remote.get("TriggerMode") != mode:  # set camera to external trigger mode
            self.grabber.remote.set("TriggerMode", MODES[mode])
        self.grabber.remote.set("TriggerSource", SOURCES[source])
        self.grabber.remote.set("TriggerActivation", POLARITIES[polarity])
        self.log.info(f"trigger set to, mode: {mode}, source: {source}, polarity: {polarity}")
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def binning(self):
        return self._binning

    @binning.setter
    def binning(self, binning: int):
        valid_binning = list(BINNINGS.keys())
        if binning not in valid_binning:
            raise ValueError("binning must be one of %r." % valid_binning)
        self._binning = binning
        # if binning is not an integer, do it in hardware
        if not isinstance(BINNINGS[binning], int):
            self.grabber.remote.set("BinningHorizontal", BINNINGS[binning])
            self.grabber.remote.set("BinningVertical", BINNINGS[binning])
        # initialize the opencl binning program
        else:
            self.gpu_binning = GPUToolsDownSample2D(binning=int(self._binning))
        # refresh parameter values
        self._get_min_max_step_values()

    @property
    def sensor_width_px(self):
        return self.max_width_px

    @property
    def sensor_height_px(self):
        return self.max_height_px

    @property
    def mainboard_temperature_c(self):
        """get the mainboard temperature in degrees C."""
        self.grabber.remote.set("DeviceTemperatureSelector", "Mainboard")
        temperature = self.grabber.remote.get("DeviceTemperature")
        return temperature

    @property
    def sensor_temperature_c(self):
        """get the sensor temperature in degrees C."""
        self.grabber.remote.set("DeviceTemperatureSelector", "Sensor")
        temperature = self.grabber.remote.get("DeviceTemperature")
        return temperature

    def prepare(self):
        # determine bits to bytes
        if self.pixel_type == "mono8":
            bit_to_byte = 1
        else:
            bit_to_byte = 2
        # software binning, so frame size is independent of binning factor
        frame_size_mb = self.width_px * self.height_px * bit_to_byte / 1e6
        self.buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        # realloc buffers appears to be allocating ram on the pc side, not camera side.
        self.grabber.realloc_buffers(self.buffer_size_frames)  # allocate RAM buffer N frames
        self.log.info(f"buffer set to: {self.buffer_size_frames} frames")

    def start(self, frame_count: int = GENTL_INFINITE):
        """Start camera. If no frame count given, assume infinite frames"""
        if frame_count == float("inf"):
            frame_count = GENTL_INFINITE
        self.grabber.start(frame_count=frame_count)

    def stop(self):
        self.grabber.stop()

    def abort(self):
        self.stop()

    def close(self):
        pass

    def reset(self):
        del self.grabber
        self.grabber = EGrabber(
            self.gentl,
            self.egrabber["interface"],
            self.egrabber["device"],
            self.egrabber["stream"],
            remote_required=True,
        )

    def grab_frame(self):
        """Retrieve a frame as a 2D numpy array with shape (rows, cols)."""
        # Note: creating the buffer and then "pushing" it at the end has the
        #   effect of moving the internal camera frame buffer from the output
        #   pool back to the input pool, so it can be reused.
        column_count = self.grabber.remote.get("Width")
        row_count = self.grabber.remote.get("Height")
        timeout_ms = 2000
        with Buffer(self.grabber, timeout=timeout_ms) as buffer:
            ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)  # grab pointer to new frame
            # grab frame data
            data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * column_count * row_count * 2)).contents
            # cast data to numpy array of correct size/datatype:
            image = numpy.frombuffer(data, count=int(column_count * row_count), dtype=numpy.uint16).reshape(
                (row_count, column_count)
            )
        # do software binning if != 1 and not a string for setting in egrabber
        if self._binning > 1 and isinstance(self._binning, int):
            image = np.copy(self.gpu_binning.run(image))
        self._latest_frame = np.copy(image)
        return image

    @property
    def latest_frame(self):
        return self._latest_frame

    def signal_acquisition_state(self):
        """return a dict with the state of the acquisition buffers"""
        # Detailed description of constants here:
        # https://documentation.euresys.com/Products/Coaxlink/Coaxlink/en-us/Content/IOdoc/egrabber-reference/
        # namespace_gen_t_l.html#a6b498d9a4c08dea2c44566722699706e
        state = {}
        state["Frame Index"] = self.grabber.stream.get_info(STREAM_INFO_NUM_DELIVERED, INFO_DATATYPE_SIZET)
        state["Input Buffer Size"] = self.grabber.stream.get_info(STREAM_INFO_NUM_QUEUED, INFO_DATATYPE_SIZET)
        state["Output Buffer Size"] = self.grabber.stream.get_info(STREAM_INFO_NUM_AWAIT_DELIVERY, INFO_DATATYPE_SIZET)
        # number of underrun, i.e. dropped frames
        state["Dropped Frames"] = self.grabber.stream.get_info(STREAM_INFO_NUM_UNDERRUN, INFO_DATATYPE_SIZET)
        # adjust data rate based on internal software binning
        state["Data Rate [MB/s]"] = self.grabber.stream.get("StatisticsDataRate") / self._binning**2
        state["Frame Rate [fps]"] = self.grabber.stream.get("StatisticsFrameRate")
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

    def log_metadata(self):
        """Log camera metadata with the schema tag."""
        # log egrabber camera settings
        self.log.info("egrabber camera parameters")
        categories = self.grabber.device.get(query.categories())
        for category in categories:
            features = self.grabber.device.get(query.features_of(category))
            for feature in features:
                if self.grabber.device.get(query.available(feature)):
                    if self.grabber.device.get(query.readable(feature)):
                        if not self.grabber.device.get(query.command(feature)):
                            self.log.info(f"device, {feature}, {self.grabber.device.get(feature)}")

        categories = self.grabber.remote.get(query.categories())
        for category in categories:
            features = self.grabber.remote.get(query.features_of(category))
            for feature in features:
                if self.grabber.remote.get(query.available(feature)):
                    if self.grabber.remote.get(query.readable(feature)):
                        if not self.grabber.remote.get(query.command(feature)):
                            if feature != "BalanceRatioSelector" and feature != "BalanceWhiteAuto":
                                self.log.info(f"remote, {feature}, {self.grabber.remote.get(feature)}")

        categories = self.grabber.stream.get(query.categories())
        for category in categories:
            features = self.grabber.stream.get(query.features_of(category))
            for feature in features:
                if self.grabber.stream.get(query.available(feature)):
                    if self.grabber.stream.get(query.readable(feature)):
                        if not self.grabber.stream.get(query.command(feature)):
                            self.log.info(f"stream, {feature}, {self.grabber.stream.get(feature)}")

        categories = self.grabber.interface.get(query.categories())
        for category in categories:
            features = self.grabber.interface.get(query.features_of(category))
            for feature in features:
                if self.grabber.interface.get(query.available(feature)):
                    if self.grabber.interface.get(query.readable(feature)):
                        if not self.grabber.interface.get(query.command(feature)):
                            self.log.info(f"interface, {feature}, {self.grabber.interface.get(feature)}")

        categories = self.grabber.system.get(query.categories())
        for category in categories:
            features = self.grabber.system.get(query.features_of(category))
            for feature in features:
                if self.grabber.system.get(query.available(feature)):
                    if self.grabber.system.get(query.readable(feature)):
                        if not self.grabber.system.get(query.command(feature)):
                            self.log.info(f"system, {feature}, {self.grabber.system.get(feature)}")

    def _update_parameters(self):
        # grab min/max parameter values
        self._get_min_max_step_values()
        # check binning options
        self._query_binning()
        # check pixel types options
        self._query_pixel_types()
        # check bit packing options
        self._query_bit_packing_modes()
        # check trigger mode options
        self._query_trigger_modes()
        # check trigger source options
        self._query_trigger_sources()
        # check trigger polarity options
        self._query_trigger_polarities()

    def _get_min_max_step_values(self):
        # gather min max values. all may not be available for certain cameras.
        # minimum exposure time
        # convert from us to ms
        try:
            self.min_exposure_time_ms = self.grabber.remote.get("ExposureTime.Min") / 1e3
            type(self).exposure_time_ms.minimum = self.min_exposure_time_ms
            self.log.debug(f"min exposure time is: {self.min_exposure_time_ms} ms")
        except:
            self.log.debug(f"min exposure time not available for camera {self.id}")
        # maximum exposure time
        # convert from us to ms
        try:
            self.max_exposure_time_ms = self.grabber.remote.get("ExposureTime.Max") / 1e3
            type(self).exposure_time_ms.maximum = self.max_exposure_time_ms
            self.log.debug(f"max exposure time is: {self.max_exposure_time_ms} ms")
        except:
            self.log.debug(f"max exposure time not available for camera {self.id}")
        # minimum width
        try:
            self.min_width_px = self.grabber.remote.get("Width.Min")
            type(self).width_px.minimum = self.min_width_px
            self.log.debug(f"min width is: {self.min_width_px} px")
        except:
            self.log.debug(f"min width not available for camera {self.id}")
        # maximum width
        try:
            self.max_width_px = self.grabber.remote.get("Width.Max")
            type(self).width_px.maximum = self.max_width_px
            self.log.debug(f"max width is: {self.max_width_px} px")
        except:
            self.log.debug(f"max width not available for camera {self.id}")
        # minimum height
        try:
            self.min_height_px = self.grabber.remote.get("Height.Min")
            type(self).height_px.minimum = self.min_height_px
            self.log.debug(f"min height is: {self.min_height_px} px")
        except:
            self.log.debug(f"min height not available for camera {self.id}")
        # maximum height
        try:
            self.max_height_px = self.grabber.remote.get("Height.Max")
            type(self).height_px.maximum = self.max_height_px
            self.log.debug(f"max height is: {self.max_height_px} px")
        except:
            self.log.debug(f"max height not available for camera {self.id}")
        # minimum offset x
        try:
            self.min_offset_x_px = self.grabber.remote.get("OffsetX.Min")
            self.log.debug(f"min offset x is: {self.min_offset_x_px} px")
        except:
            self.log.debug(f"min offset x not available for camera {self.id}")
        # maximum offset x
        try:
            self.max_offset_x_px = self.grabber.remote.get("OffsetX.Max")
            self.log.debug(f"max offset x is: {self.max_offset_x_px} px")
        except:
            self.log.debug(f"max offset x not available for camera {self.id}")
        # minimum offset y
        try:
            self.min_offset_y_px = self.grabber.remote.get("OffsetY.Min")
            self.log.debug(f"min offset y is: {self.min_offset_y_px} px")
        except:
            self.log.debug(f"min offset y not available for camera {self.id}")
        # maximum offset y
        try:
            self.max_offset_y_px = self.grabber.remote.get("OffsetY.Max")
            self.log.debug(f"max offset y is: {self.max_offset_y_px} px")
        except:
            self.log.debug(f"max offset y not available for camera {self.id}")
        # step exposure time
        # convert from us to ms
        try:
            self.step_exposure_time_ms = self.grabber.remote.get("ExposureTime.Inc") / 1e3
            type(self).exposure_time_ms.step = self.step_exposure_time_ms
            self.log.debug(f"step exposure time is: {self.step_exposure_time_ms} ms")
        except:
            self.log.debug(f"step exposure time not available for camera {self.id}")
        # step width
        try:
            self.step_width_px = self.grabber.remote.get("Width.Inc")
            type(self).width_px.step = self.step_width_px
            self.log.debug(f"step width is: {self.step_width_px} px")
        except:
            self.log.debug(f"step width not available for camera {self.id}")
        # step height
        try:
            self.step_height_px = self.grabber.remote.get("Height.Inc")
            type(self).height_px.step = self.step_height_px
            self.log.debug(f"step height is: {self.step_height_px} px")
        except:
            self.log.debug(f"step height not available for camera {self.id}")
        # step offset x
        try:
            self.step_offset_x_px = self.grabber.remote.get("OffsetX.Inc")
            self.log.debug(f"step offset x is: {self.step_offset_x_px} px")
        except:
            self.log.debug(f"step offset x not available for camera {self.id}")
        # step offset y
        try:
            self.step_offset_y_px = self.grabber.remote.get("OffsetY.Inc")
            self.log.debug(f"step offset y is: {self.step_offset_y_px} px")
        except:
            self.log.debug(f"step offset y not available for camera {self.id}")

    def _query_binning(self):
        # egrabber defines 1 as 'X1', 2 as 'X2', 3 as 'X3'...
        # check only horizontal since we will use same binning for vertical
        binning_options = self.grabber.remote.get("@ee BinningHorizontal", dtype=list)
        init_binning = self.grabber.remote.get("BinningHorizontal")
        for binning in binning_options:
            try:
                self.grabber.remote.set("BinningHorizontal", binning)
                # generate integer key
                key = int(binning.replace("X", ""))
                BINNINGS[key] = binning
            except:
                self.log.debug(f"{binning} not avaiable on this camera")
                # only implement software binning for even numbers
                if int(binning.replace("X", "")) % 2 == 0:
                    self.log.debug(f"{binning} will be implemented through software")
                    key = int(binning.replace("X", ""))
                    BINNINGS[key] = key
        # reset to initial value
        self.grabber.remote.set("BinningHorizontal", init_binning)

    def _query_pixel_types(self):
        # egrabber defines as 'Mono8', 'Mono12', 'Mono16'...
        pixel_type_options = self.grabber.remote.get("@ee PixelFormat", dtype=list)
        init_pixel_type = self.grabber.remote.get("PixelFormat")
        for pixel_type in pixel_type_options:
            try:
                self.grabber.remote.set("PixelFormat", pixel_type)
                # generate lowercase string key
                key = pixel_type.lower()
                PIXEL_TYPES[key] = pixel_type
            except:
                self.log.debug(f"{pixel_type} not avaiable on this camera")

        # once the pixel types are found, determine line intervals
        self._query_line_intervals()
        # reset to initial value
        self.grabber.remote.set("PixelFormat", init_pixel_type)

    def _query_bit_packing_modes(self):
        # egrabber defines as 'Msb', 'Lsb', 'None'...
        bit_packing_options = self.grabber.stream.get("@ee UnpackingMode", dtype=list)
        init_bit_packing = self.grabber.stream.get("UnpackingMode")
        for bit_packing in bit_packing_options:
            try:
                self.grabber.stream.set("UnpackingMode", bit_packing)
                # generate lowercase string key
                key = bit_packing.lower()
                BIT_PACKING_MODES[key] = bit_packing
            except:
                self.log.debug(f"{bit_packing} not avaiable on this camera")
        # reset to initial value
        self.grabber.stream.set("UnpackingMode", init_bit_packing)

    def _query_line_intervals(self):
        # based on framerate and number of sensor rows
        for key in PIXEL_TYPES:
            # set pixel type
            self.grabber.remote.set("PixelFormat", PIXEL_TYPES[key])
            # check max acquisition rate, used to determine line interval
            max_frame_rate = self.grabber.remote.get("AcquisitionFrameRate.Max")
            # vp-151mx camera uses the sony imx411 camera which has 10640 active rows
            # but 10802 total rows. from the manual 10760 are used during readout
            if self.grabber.remote.get("DeviceModelName") == "VP-151MX-M6H0":
                line_interval_s = (1 / max_frame_rate) / (self.sensor_height_px + 120)
            else:
                line_interval_s = (1 / max_frame_rate) / self.sensor_height_px
            # conver from s to us and store
            LINE_INTERVALS_US[key] = line_interval_s * 1e6

    def _query_trigger_modes(self):
        trigger_mode_options = self.grabber.remote.get("@ee TriggerMode", dtype=list)
        init_trigger_mode = self.grabber.remote.get("TriggerMode")
        for trigger_mode in trigger_mode_options:
            # note: setting TriggerMode to the already set value throws an error
            # so check the current value and only set if new value
            if self.grabber.remote.get("TriggerMode") != trigger_mode:  # set camera to external trigger mode
                try:
                    self.grabber.remote.set("TriggerMode", trigger_mode)
                    # generate lowercase string key
                    key = trigger_mode.lower()
                    MODES[key] = trigger_mode
                except:
                    self.log.debug(f"{trigger_mode} not avaiable on this camera")
            # if it is already set to this value, we know that it is a valid setting
            else:
                key = trigger_mode.lower()
                MODES[key] = trigger_mode
        # reset to initial value
        self.grabber.remote.set("TriggerMode", init_trigger_mode)

    def _query_trigger_sources(self):
        trigger_source_options = self.grabber.remote.get("@ee TriggerSource", dtype=list)
        init_trigger_source = self.grabber.remote.get("TriggerSource")
        for trigger_source in trigger_source_options:
            try:
                self.grabber.remote.set("TriggerSource", trigger_source)
                # generate lowercase string key
                key = trigger_source.lower()
                SOURCES[key] = trigger_source
            except:
                self.log.debug(f"{trigger_source} not avaiable on this camera")
        # reset to initial value
        self.grabber.remote.set("TriggerSource", init_trigger_source)

    def _query_trigger_polarities(self):
        trigger_polarity_options = self.grabber.remote.get("@ee TriggerActivation", dtype=list)
        init_trigger_polarity = self.grabber.remote.get("TriggerActivation")
        for trigger_polarity in trigger_polarity_options:
            try:
                self.grabber.remote.set("TriggerActivation", trigger_polarity)
                # generate lowercase string key
                key = trigger_polarity.lower()
                POLARITIES[key] = trigger_polarity
            except:
                self.log.debug(f"{trigger_polarity} not avaiable on this camera")
        # reset to initial value
        self.grabber.remote.set("TriggerActivation", init_trigger_polarity)

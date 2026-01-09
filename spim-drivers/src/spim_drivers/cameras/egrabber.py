import logging
import math
from dataclasses import dataclass, field
from typing import Any, cast, final

import numpy as np
from egrabber import (
    BUFFER_INFO_BASE,
    GENTL_INFINITE,
    INFO_DATATYPE_PTR,
    Buffer,
    EGenTL,
    EGrabber,
    EGrabberDiscovery,
    GenTLException,
    RemoteModule,
    StreamModule,
    ct,
)
from ome_zarr_writer.types import Vec2D
from spim_drivers.utils import thread_safe_singleton
from spim_rig.camera.base import (
    FrameRegion,
    PixelFormat,
    SpimCamera,
    StreamInfo,
    TriggerMode,
    TriggerPolarity,
)
from spim_rig.helpers import parse_vec2d

from pyrig.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string


@thread_safe_singleton
def get_egentl_singleton() -> EGenTL:
    return EGenTL()


@dataclass
class EgrabberDevice:
    grabber: EGrabber
    remote: RemoteModule
    stream: StreamModule
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("EgrabberDevice"))

    def fetch_remote[T](self, feature: str, dtype: type[T]) -> T:
        value = self.remote.get(feature=feature, dtype=dtype)
        if value is None:
            err = f"Failed to get remote property: {feature}"
            raise RuntimeError(err)
        return value

    def set_remote(self, feature: str, value: Any) -> None:
        if not self.remote:
            self.logger.error("Unable to set %s. Remote component is not available.", feature)
            return
        self.remote.set(feature=feature, value=value)


def fetch_devices() -> dict[str, "EgrabberDevice"]:
    devices: dict[str, EgrabberDevice] = {}

    gentl = get_egentl_singleton()
    discovery = EGrabberDiscovery(gentl=gentl)
    discovery.discover()
    for cam in discovery.cameras:
        grabber = EGrabber(data=cam)
        remote = grabber.remote
        stream = grabber.stream
        if remote and stream and (ser := remote.get("DeviceSerialNumber", dtype=str)):
            devices[ser] = EgrabberDevice(grabber=grabber, remote=remote, stream=stream)
    return devices


def get_dev_by_serial(serial_number: str) -> "EgrabberDevice":
    devices = fetch_devices()
    if serial_number not in devices:
        err = f"Serial number {serial_number} not found. Available devices: {list(devices.keys())}"
        raise RuntimeError(err)
    return devices[serial_number]


@dataclass
class Binning:
    raw: str = "X1"
    raw_options: list[str] = field(default_factory=lambda: ["X1"])

    @property
    def value(self) -> int:
        return self.parse_str(self.raw)

    @property
    def options(self) -> list[int]:
        sorted_options = sorted([self.parse_str(b) for b in set(self.raw_options)])
        return list(sorted_options)

    @staticmethod
    def parse_str(binning_str: str) -> int:
        try:
            return int(binning_str[1:])
        except (ValueError, IndexError) as e:
            err_msg = f"Invalid binning string: {binning_str}"
            raise ValueError(err_msg) from e


@dataclass
class MinMaxIncProp:
    val: float
    min: float
    max: float
    inc: float = 1.0


@dataclass
class MinMaxProp:
    val: float
    min: float
    max: float


@dataclass
class ExposureTime(MinMaxIncProp):
    pass


@final
class VieworksCamera(SpimCamera):
    BUFFER_SIZE_MB = 4096  # 4 GB

    def __init__(
        self,
        uid: str,
        serial: str,
        pixel_size_um: Vec2D[float] | list[float] | str = Vec2D(y=1.0, x=1.0),
    ):
        super().__init__(uid=uid)
        self._pixel_size_um = parse_vec2d(pixel_size_um, rtype=float)
        self._dev = get_dev_by_serial(serial)

        # cache static properties
        self._sensor_size_px: Vec2D[int] = self._query_sensor_size_px()
        self._trigger_source_opts = self._query_trigger_sources()
        self._pixel_format_options: list[PixelFormat] = self._query_pixel_format_options()

        # constrained properties
        self._binning = Binning()
        self._exposure_ms = ExposureTime(min=float("-inf"), max=float("inf"), val=10.0)
        self._frame_rate_hz = MinMaxProp(min=0.0, max=12.0, val=3.0)
        self._refresh_binning_info()
        self._refresh_exposure_ms()

    @property
    def sensor_size_px(self) -> Vec2D[int]:
        return self._sensor_size_px

    @property
    def pixel_size_um(self) -> Vec2D[float]:
        return self._pixel_size_um

    @enumerated_string(options=lambda self: self._pixel_format_options)
    def pixel_format(self) -> PixelFormat:
        fmt = self._dev.fetch_remote(feature="PixelFormat", dtype=str)
        return cast("PixelFormat", fmt.upper())

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        if self.pixel_format != pixel_format.upper():
            self.log.info("pixel_format updated: %s -> %s", self.pixel_format, pixel_format.upper())
            self._dev.remote.set("PixelFormat", pixel_format.capitalize())
            self._refresh_binning_info()
            self._refresh_exposure_ms()

    @enumerated_int(options=lambda self: list(self._binning.options))
    def binning(self) -> int:
        return self._binning.value

    @binning.setter
    def binning(self, binning: int) -> None:
        try:
            self._dev.remote.set(feature="BinningHorizontal", value=int(binning))
            self._dev.remote.set(feature="BinningVertical", value=int(binning))
            self.log.info("Set binning to %dx%d", binning, binning)
        except GenTLException:
            self.log.exception("Failed to set binning")
        finally:
            self._refresh_binning_info()
            self._refresh_exposure_ms()

    @deliminated_float(min_value=lambda self: self._exposure_ms.min, max_value=lambda self: self._exposure_ms.max)
    def exposure_time_ms(self) -> int:
        if exp_time := self._dev.remote.get(feature="ExposureTime", dtype=float):
            return int(exp_time / 1000)
        return 0

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        self._dev.set_remote(feature="ExposureTime", value=exposure_time_ms * 1000)
        self.log.info("Set exposure time to %s ms", self._exposure_ms.val)
        self._refresh_exposure_ms()

    @deliminated_float(min_value=lambda self: self._frame_rate_hz.min, max_value=lambda self: self._frame_rate_hz.max)
    def frame_rate_hz(self) -> float:
        if frame_rate := self._dev.remote.get(feature="AcquisitionFrameRate", dtype=float):
            return frame_rate
        return 0.0

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        self._dev.set_remote(feature="AcquisitionFrameRate", value=value)
        self.log.info("Set frame rate to %s Hz", self._frame_rate_hz.val)
        self._refresh_exposure_ms()

    @property
    def stream_info(self) -> StreamInfo | None:
        if not self._dev.fetch_remote("AcquisitionStatus", dtype=bool):
            return None
        return StreamInfo(
            frame_index=-1,
            input_buffer_size=-1,
            output_buffer_size=-1,
            dropped_frames=-1,
            data_rate_mbs=-1,
            frame_rate_fps=-1,
        )

    @property
    def frame_region(self) -> FrameRegion:
        """Get current frame region with embedded constraints."""
        return FrameRegion(
            x=DeliminatedInt(
                self._dev.fetch_remote("OffsetX", int),
                min_value=0,
                max_value=self._dev.fetch_remote("OffsetX.Max", int),
                step=self._dev.fetch_remote("OffsetX.Inc", int),
            ),
            y=DeliminatedInt(
                self._dev.fetch_remote("OffsetY", int),
                min_value=0,
                max_value=self._dev.fetch_remote("OffsetY.Max", int),
                step=self._dev.fetch_remote("OffsetY.Inc", int),
            ),
            width=DeliminatedInt(
                self._dev.fetch_remote("Width", int),
                min_value=self._dev.fetch_remote("Width.Min", int),
                max_value=self._dev.fetch_remote("Width.Max", int),
                step=self._dev.fetch_remote("Width.Inc", int),
            ),
            height=DeliminatedInt(
                self._dev.fetch_remote("Height", int),
                min_value=self._dev.fetch_remote("Height.Min", int),
                max_value=self._dev.fetch_remote("Height.Max", int),
                step=self._dev.fetch_remote("Height.Inc", int),
            ),
        )

    def update_frame_region(
        self,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Update frame region. Only provided values are changed."""
        # Set dimensions first (may need to reduce size before changing offset)
        if width is not None:
            self._dev.remote.set("Width", width)
        if height is not None:
            self._dev.remote.set("Height", height)
        if x is not None:
            self._dev.remote.set("OffsetX", x)
        if y is not None:
            self._dev.remote.set("OffsetY", y)

    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        curr_on_off = self._dev.fetch_remote("TriggerMode", str)
        if mode == TriggerMode.OFF and curr_on_off != "Off":
            self._dev.remote.set("TriggerMode", "Off")
            return
        if mode == TriggerMode.ON and curr_on_off != "On":
            self._dev.remote.set("TriggerMode", "On")
        curr_source = self._dev.fetch_remote("TriggerSource", str)
        if "Line0" in self._trigger_source_opts and curr_source != "Line0":
            self._dev.remote.set("TriggerSource", "Line0")
        # self._dev.remote.set('TriggerSelector', 'ExposureStart')

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        match polarity:
            case TriggerPolarity.RISING_EDGE:
                self._dev.remote.set("TriggerActivation", "RisingEdge")
            case TriggerPolarity.FALLING_EDGE:
                self._dev.remote.set("TriggerActivation", "FallingEdge")

    def _prepare_for_capture(self) -> None:
        """Prepare the camera to acquire images.

        This method sets up the camera buffer for Vieworks cameras.
        It calculates the appropriate buffer size based on the current camera settings
        and allocates the buffer in PC RAM.
        :raises RuntimeError: If the camera preparation fails.
        """
        num_frames = max(1, round(self.BUFFER_SIZE_MB / self.frame_size_mb))
        self._dev.grabber.realloc_buffers(num_frames)

        self.log.info("Prepared camera with buffer for %s frames", num_frames)

    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire a certain number of frames.

        If frame number is not specified, acquires infinitely until stopped.
        Initializes the camera buffer.
        """
        frame_count = GENTL_INFINITE if frame_count is None else frame_count

        self._dev.grabber.start(frame_count)
        self.log.info("Camera started. Requesting %s frames ...", frame_count)
        raw = self._dev.remote.get("AcquisitionStatus", dtype=str)
        self.log.debug("AcquisitionStatus: %s", raw)

    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer."""
        # Note: creating the buffer and then "pushing" it at the end has the
        #   effect of moving the internal camera frame buffer from the output
        #   pool back to the input pool, so it can be reused.
        frame_time_ms = math.ceil(1000 / self.frame_rate_hz)
        input_buf_frame_count = math.ceil(self.BUFFER_SIZE_MB / self.frame_size_mb)
        timeout_ms = frame_time_ms * input_buf_frame_count * 2

        timeout_ms = max(2000, timeout_ms)

        with Buffer(self._dev.grabber, timeout=timeout_ms) as buffer:
            ptr = buffer.get_info(BUFFER_INFO_BASE, INFO_DATATYPE_PTR)
            assert isinstance(ptr, int), f"Expected pointer to be of type int, got {type(ptr)}"

            # Get actual buffer dimensions directly from camera (not frame_size_px which divides by binning)
            # The camera's Width/Height already reflects hardware binning
            column_count = self._dev.fetch_remote("Width", int)
            row_count = self._dev.fetch_remote("Height", int)
            bytes_per_pixel = 2 if self.pixel_type.dtype == np.uint16 else 1

            # Read frame data directly (matches old working driver)
            buffer_size = column_count * row_count * bytes_per_pixel
            data = ct.cast(ptr, ct.POINTER(ct.c_ubyte * buffer_size)).contents
            frame = np.frombuffer(data, count=column_count * row_count, dtype=self.pixel_type.dtype)
            return frame.reshape((row_count, column_count))

    def stop(self) -> None:
        """Stop the camera from acquiring frames."""
        try:
            self._dev.grabber.stop()
            # Reset stream to ensure clean state for next acquisition
            # bit_packing_mode = self._dev.stream.get("UnpackingMode")
            # self._dev.stream.execute("StreamReset")
            # self._dev.stream.set("UnpackingMode", bit_packing_mode)
            self.log.info("Camera stopped successfully.")
        except GenTLException as e:
            self.log.warning("EGrabber error when attempting to stop camera. Error: %s", e)
        except Exception:
            self.log.exception("Failed to stop camera")

    def _refresh_binning_info(self) -> None:
        if not self._dev.remote:
            raise RuntimeError("Unable to query binning options. Remote component is not available.")
        h = self._dev.fetch_remote("BinningHorizontal", str)
        raw_h_options = set(self._dev.fetch_remote(feature="@ee BinningHorizontal", dtype=list))
        raw_v_options = set(self._dev.fetch_remote(feature="@ee BinningVertical", dtype=list))
        raw_h_options = raw_v_options = raw_h_options.union(raw_v_options) or {"X1"}

        h_options = []
        skipped_options = set()
        for opt in raw_h_options:
            try:
                self._dev.remote.set(feature="BinningHorizontal", value=opt)
                self._dev.remote.set(feature="BinningVertical", value=opt)
                h_options.append(opt)
            except GenTLException:
                skipped_options.add(opt)
        if skipped_options:
            ...
            # self.log.debug('Skipped unsupported binning options: %s', skipped_options)

        if h not in h_options:
            h = h_options[0]

        self._binning = Binning(raw=h, raw_options=h_options)

        self._dev.remote.set(feature="BinningHorizontal", value=h)
        self._dev.remote.set(feature="BinningVertical", value=h)

    def _refresh_exposure_ms(self) -> None:
        min_exp = self._dev.fetch_remote("ExposureTime.Min", int)
        max_exp = self._dev.fetch_remote("ExposureTime.Max", int)
        cur_exp = self._dev.fetch_remote("ExposureTime", int)
        self._exposure_ms = ExposureTime(min=min_exp / 1000, max=max_exp / 1000, val=cur_exp / 1000)
        self._frame_rate_hz = MinMaxProp(
            min=self._dev.fetch_remote("AcquisitionFrameRate.Min", float),
            max=self._dev.fetch_remote("AcquisitionFrameRate.Max", float),
            val=self._dev.fetch_remote("AcquisitionFrameRate", float),
        )

    def _query_sensor_size_px(self) -> Vec2D[int]:
        x = self._dev.fetch_remote(feature="SensorWidth", dtype=int)
        y = self._dev.fetch_remote(feature="SensorHeight", dtype=int)
        return Vec2D(x=x, y=y)

    def _query_trigger_sources(self) -> set[str]:
        """Query the available trigger sources."""
        trigger_source_options = self._dev.remote.get("@ee TriggerSource", dtype=list)
        init_trigger_source = self._dev.remote.get("TriggerSource")

        opts = set()

        for trigger_source in trigger_source_options:
            try:
                self._dev.remote.set("TriggerSource", trigger_source)
                opts.add(trigger_source)
            except Exception:  # noqa: BLE001, S110
                pass
        # reset to initial value
        self._dev.remote.set("TriggerSource", init_trigger_source)
        return opts

    def _query_pixel_format_options(self) -> list[PixelFormat]:
        """Internal function that queries camera SDK to determine pixel type options.

        Note:
            EGrabber defines pixel format settings as strings: 'Mono8', 'Mono12' 'Mono16' etc.

        """
        options: list[PixelFormat] = []
        initial = None
        try:
            initial = self._dev.remote.get("PixelFormat")
            raw_options = self._dev.remote.get("@ee PixelFormat", dtype=list)
            for option in raw_options:
                try:
                    self._dev.remote.set("PixelFormat", option)
                    options.append(option.upper())
                except Exception as e:  # noqa: BLE001
                    self.log.debug("Unexpected error processing pixel format: %s. Error: %s", option, e)
        finally:
            if initial:
                try:
                    self._dev.remote.set("PixelFormat", initial)
                except Exception:
                    self.log.exception("Failed to restore initial pixel format %s", initial)
            self.log.debug("Completed querying pixel format options: %s", options)
        return options

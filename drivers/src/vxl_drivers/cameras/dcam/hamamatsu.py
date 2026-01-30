"""Hamamatsu camera driver using DCAM SDK."""

import time

import numpy as np
from rigup.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string
from vxlib.vec import IVec2D, Vec2D

from rigup import describe
from vxl.camera.base import Camera, FrameRegion, PixelFormat, StreamInfo, TriggerMode, TriggerPolarity
from vxlib import thread_safe_singleton

from .sdk.dcam import DCAM_IDSTR, DCAMERR, DCAMPROP_ATTR, Dcam, Dcamapi
from .sdk.dcamapi4 import DCAMCAP_TRANSFERINFO


def _unwrap[T](result: T | bool, default: T) -> T:
    """Unwrap DCAM SDK result that returns False on error."""
    return default if result is False else result  # type: ignore[return-value]


# Default property attributes for fallback
_DEFAULT_ATTR = DCAMPROP_ATTR()
_DEFAULT_ATTR.valuemin = 0.0
_DEFAULT_ATTR.valuemax = 1.0
_DEFAULT_ATTR.valuestep = 1.0

# Buffer size in MB for frame storage
BUFFER_SIZE_MB = 2400

# DCAM property IDs
_PROPS = {
    "exposure_time": 0x001F0110,
    "sensor_mode": 0x00400210,
    "binning": 0x00401110,
    "readout_direction": 0x00400130,
    "trigger_active": 0x00100120,
    "trigger_mode": 0x00100210,
    "trigger_polarity": 0x00100220,
    "trigger_source": 0x00100110,
    "line_interval": 0x00403850,
    "image_width": 0x00420210,
    "image_height": 0x00420220,
    "subarray_hpos": 0x00402110,
    "subarray_hsize": 0x00402120,
    "subarray_vpos": 0x00402130,
    "subarray_vsize": 0x00402140,
    "subarray_mode": 0x00402150,
    "pixel_type": 0x00420270,
    "sensor_temperature": 0x00200310,
}

# Pixel format mapping: DCAM format -> Camera format
_DCAM_TO_PIXEL_FMT: dict[str, PixelFormat] = {
    "mono8": "MONO8",
    "mono12": "MONO12",
    "mono16": "MONO16",
}

_PIXEL_FMT_TO_DCAM: dict[PixelFormat, str] = {v: k for k, v in _DCAM_TO_PIXEL_FMT.items()}


@thread_safe_singleton
def _get_dcamapi() -> Dcamapi:
    """Get the singleton Dcamapi instance."""
    return Dcamapi()


class HamamatsuCamera(Camera):
    """Hamamatsu camera driver using DCAM SDK.

    Supports Hamamatsu sCMOS cameras like ORCA-Flash and ORCA-Fusion.
    """

    def __init__(
        self,
        uid: str,
        serial: str,
        pixel_size_um: Vec2D | tuple[float, float] | list[float] | str = (6.5, 6.5),
    ) -> None:
        """Initialize the Hamamatsu camera.

        Args:
            uid: Unique identifier for this device.
            serial: Camera serial number.
            pixel_size_um: Physical pixel size in microns (y, x). Default is 6.5µm for ORCA.
        """
        super().__init__(uid=uid)

        self._serial = str(serial)
        self._pixel_size_um = pixel_size_um if isinstance(pixel_size_um, Vec2D) else Vec2D.parse(pixel_size_um)
        self._latest_frame: np.ndarray | None = None
        self._buffer_size_frames = 0
        self._dropped_frames = 0
        self._pre_frame_time = 0.0
        self._pre_frame_count = 0

        # Initialize DCAM API
        dcamapi = _get_dcamapi()
        if dcamapi.init() is False:
            raise RuntimeError(f"DCAM API init failed: {DCAMERR(dcamapi.lasterr()).name}")

        # Find and open camera by serial number
        self._dcam: Dcam | None = None
        self._cam_index = -1
        num_cams = dcamapi.get_devicecount()

        for i in range(num_cams):
            dcam = Dcam(i)
            cam_id = dcam.dev_getstring(DCAM_IDSTR.CAMERAID)
            if cam_id and cam_id.replace("S/N: ", "") == self._serial:
                self._dcam = dcam
                self._cam_index = i
                self._dcam.dev_open()
                break

        if self._dcam is None:
            raise ValueError(f"No camera found for S/N: {self._serial}")

        # Cache sensor dimensions
        self._sensor_width = int(_unwrap(self._dcam.prop_getattr(_PROPS["image_width"]), _DEFAULT_ATTR).valuemax)
        self._sensor_height = int(_unwrap(self._dcam.prop_getattr(_PROPS["image_height"]), _DEFAULT_ATTR).valuemax)

        # Query available options from driver
        self._binning_options = self._query_binning_options()
        self._pixel_format_options = self._query_pixel_format_options()
        self._sensor_mode_options = self._query_sensor_mode_options()
        self._readout_direction_options = self._query_readout_direction_options()

        self.log.info(
            f"Initialized Hamamatsu camera: serial={serial}, sensor={self._sensor_width}x{self._sensor_height}",
        )

    @property
    def _cam(self) -> Dcam:
        """Get camera instance, raising if not initialized."""
        if self._dcam is None:
            raise RuntimeError("Camera not initialized")
        return self._dcam

    # ==================== Sensor Properties ====================

    @property
    @describe(label="Sensor Size", units="px", desc="The size of the camera sensor in pixels.")
    def sensor_size_px(self) -> IVec2D:
        """Get the size of the camera sensor in pixels."""
        return IVec2D(y=self._sensor_height, x=self._sensor_width)

    @property
    @describe(label="Pixel Size", units="µm", desc="The size of the camera pixel in microns.")
    def pixel_size_um(self) -> Vec2D:
        """Get the size of the camera pixel in microns."""
        return self._pixel_size_um

    # ==================== Pixel Format ====================

    @enumerated_string(options=lambda self: self._pixel_format_options)
    def pixel_format(self) -> PixelFormat:
        """Get the pixel format of the camera."""
        dcam_type = _unwrap(self._cam.prop_getvalue(_PROPS["pixel_type"]), 0.0)
        # Find matching format from our queried options
        for dcam_name, pixel_fmt in _DCAM_TO_PIXEL_FMT.items():
            if dcam_name in self._pixel_type_map and self._pixel_type_map[dcam_name] == dcam_type:
                return pixel_fmt
        return "MONO16"

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel format of the camera."""
        if pixel_format not in self._pixel_format_options:
            raise ValueError(f"Invalid pixel format: {pixel_format}. Valid: {self._pixel_format_options}")

        dcam_name = _PIXEL_FMT_TO_DCAM.get(pixel_format, "mono16").lower()
        if dcam_name in self._pixel_type_map:
            self._cam.prop_setvalue(_PROPS["pixel_type"], self._pixel_type_map[dcam_name])
            self.log.debug(f"Pixel format set to {pixel_format}")

    # ==================== Binning ====================

    @enumerated_int(options=lambda self: self._binning_options)
    def binning(self) -> int:
        """Get the binning mode of the camera."""
        return int(_unwrap(self._cam.prop_getvalue(_PROPS["binning"]), 1.0))

    @binning.setter
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera."""
        if binning not in self._binning_options:
            raise ValueError(f"Invalid binning: {binning}. Valid: {self._binning_options}")
        self._cam.prop_setvalue(_PROPS["binning"], binning)
        self.log.debug(f"Binning set to {binning}x{binning}")

    # ==================== Exposure & Frame Rate ====================

    @deliminated_float(
        min_value=lambda self: _unwrap(self._cam.prop_getattr(_PROPS["exposure_time"]), _DEFAULT_ATTR).valuemin * 1000,
        max_value=lambda self: _unwrap(self._cam.prop_getattr(_PROPS["exposure_time"]), _DEFAULT_ATTR).valuemax * 1000,
        step=0.001,
    )
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms."""
        return _unwrap(self._cam.prop_getvalue(_PROPS["exposure_time"]), 0.01) * 1000  # s to ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms."""
        self._cam.prop_setvalue(_PROPS["exposure_time"], exposure_time_ms / 1000)  # ms to s
        self.log.debug(f"Exposure time set to {exposure_time_ms} ms")

    @deliminated_float(min_value=0.1, max_value=1000.0, step=0.1)
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz."""
        frame_time_ms = self._get_frame_time_ms()
        return 1000 / frame_time_ms if frame_time_ms > 0 else 0

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate of the camera in Hz."""
        del value  # unused - frame rate controlled via line interval
        self.log.warning("Frame rate is controlled via line interval on Hamamatsu cameras")

    def _get_frame_time_ms(self) -> float:
        """Calculate frame time based on sensor mode."""
        line_interval_us = _unwrap(self._cam.prop_getvalue(_PROPS["line_interval"]), 0.0) * 1e6
        region = self.frame_region
        exposure_ms = self.exposure_time_ms

        sensor_mode = self._get_sensor_mode_name()
        if sensor_mode and "light sheet" in sensor_mode.lower():
            return (line_interval_us * int(region.height)) / 1000 + exposure_ms
        return (line_interval_us * int(region.height) / 2) / 1000 + exposure_ms

    # ==================== Frame Region ====================

    @property
    def frame_region(self) -> FrameRegion:
        """Get current frame region with embedded constraints."""
        w_attr = _unwrap(self._cam.prop_getattr(_PROPS["image_width"]), _DEFAULT_ATTR)
        h_attr = _unwrap(self._cam.prop_getattr(_PROPS["image_height"]), _DEFAULT_ATTR)

        step_x = int(w_attr.valuestep) if w_attr.valuestep > 0 else 4
        step_y = int(h_attr.valuestep) if h_attr.valuestep > 0 else 4
        min_w = int(w_attr.valuemin)
        min_h = int(h_attr.valuemin)

        return FrameRegion(
            x=DeliminatedInt(
                int(_unwrap(self._cam.prop_getvalue(_PROPS["subarray_hpos"]), 0.0)),
                min_value=0,
                max_value=self._sensor_width - min_w,
                step=step_x,
            ),
            y=DeliminatedInt(
                int(_unwrap(self._cam.prop_getvalue(_PROPS["subarray_vpos"]), 0.0)),
                min_value=0,
                max_value=self._sensor_height - min_h,
                step=step_y,
            ),
            width=DeliminatedInt(
                int(_unwrap(self._cam.prop_getvalue(_PROPS["subarray_hsize"]), float(self._sensor_width))),
                min_value=min_w,
                max_value=self._sensor_width,
                step=step_x,
            ),
            height=DeliminatedInt(
                int(_unwrap(self._cam.prop_getvalue(_PROPS["subarray_vsize"]), float(self._sensor_height))),
                min_value=min_h,
                max_value=self._sensor_height,
                step=step_y,
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
        # Reset offsets first if changing dimensions
        if width is not None or height is not None:
            self._cam.prop_setvalue(_PROPS["subarray_hpos"], 0)
            self._cam.prop_setvalue(_PROPS["subarray_vpos"], 0)

        # Set dimensions
        if width is not None:
            self._cam.prop_setvalue(_PROPS["subarray_hsize"], width)
        if height is not None:
            self._cam.prop_setvalue(_PROPS["subarray_vsize"], height)

        # Set offsets
        if x is not None:
            self._cam.prop_setvalue(_PROPS["subarray_hpos"], x)
        if y is not None:
            self._cam.prop_setvalue(_PROPS["subarray_vpos"], y)

        self.log.debug(f"Frame region updated: x={x}, y={y}, w={width}, h={height}")

    # ==================== Sensor Mode ====================

    @enumerated_string(options=lambda self: list(self._sensor_mode_options.keys()))
    @describe(label="Sensor Mode", desc="Camera sensor readout mode.")
    def sensor_mode(self) -> str:
        """Get the sensor mode."""
        return self._get_sensor_mode_name() or "area"

    @sensor_mode.setter
    def sensor_mode(self, mode: str) -> None:
        """Set the sensor mode."""
        if mode not in self._sensor_mode_options:
            raise ValueError(f"Invalid sensor mode: {mode}. Valid: {list(self._sensor_mode_options.keys())}")
        self._cam.prop_setvalue(_PROPS["sensor_mode"], self._sensor_mode_options[mode])
        self.log.debug(f"Sensor mode set to {mode}")

    def _get_sensor_mode_name(self) -> str | None:
        """Get current sensor mode name."""
        mode_val = _unwrap(self._cam.prop_getvalue(_PROPS["sensor_mode"]), 0.0)
        for name, val in self._sensor_mode_options.items():
            if val == mode_val:
                return name
        return None

    # ==================== Stream Info ====================

    @property
    @describe(label="Stream Info", desc="Acquisition state info or None if not streaming.", stream=True)
    def stream_info(self) -> StreamInfo | None:
        """Return acquisition state or None if not acquiring."""
        try:
            cap_info = self._cam.cap_transferinfo()
            if cap_info is False or not isinstance(cap_info, DCAMCAP_TRANSFERINFO):
                return None

            post_time = time.time()
            frame_index = cap_info.nFrameCount
            out_buffer_size = frame_index - self._pre_frame_count
            in_buffer_size = self._buffer_size_frames - out_buffer_size

            if out_buffer_size > self._buffer_size_frames:
                self._dropped_frames += out_buffer_size - self._buffer_size_frames

            elapsed = post_time - self._pre_frame_time if self._pre_frame_time > 0 else 1
            frame_rate = out_buffer_size / elapsed if elapsed > 0 else 0
            data_rate = frame_rate * self.frame_size_mb

            self._pre_frame_time = post_time
            self._pre_frame_count = frame_index

            return StreamInfo(
                frame_index=frame_index,
                input_buffer_size=in_buffer_size,
                output_buffer_size=out_buffer_size,
                dropped_frames=self._dropped_frames,
                frame_rate_fps=frame_rate,
                data_rate_mbs=data_rate,
            )
        except Exception:
            return None

    # ==================== Trigger Configuration ====================

    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        """Configure the trigger mode of the camera."""
        if mode == TriggerMode.ON:
            # External trigger
            self._cam.prop_setvalue(_PROPS["trigger_source"], 2)  # EXTERNAL
        else:
            # Internal trigger
            self._cam.prop_setvalue(_PROPS["trigger_source"], 1)  # INTERNAL
        self.log.debug(f"Trigger mode set to {mode}")

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        """Configure the trigger polarity of the camera."""
        if polarity == TriggerPolarity.RISING_EDGE:
            self._cam.prop_setvalue(_PROPS["trigger_polarity"], 2)  # POSITIVE
        else:
            self._cam.prop_setvalue(_PROPS["trigger_polarity"], 1)  # NEGATIVE
        self.log.debug(f"Trigger polarity set to {polarity}")

    # ==================== Acquisition ====================

    def _prepare_for_capture(self) -> None:
        """Prepare the camera to acquire images."""
        bit_to_byte = 1 if self.pixel_format == "MONO8" else 2
        frame_size_mb = self.frame_size_px.x * self.frame_size_px.y * bit_to_byte / (1024**2)
        self._buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        self._cam.buf_alloc(self._buffer_size_frames)
        self.log.debug(f"Buffer set to {self._buffer_size_frames} frames")

    @describe(label="Start", desc="Start acquiring frames from the camera.")
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire frames."""
        del frame_count  # unused - continuous acquisition
        self.log.info("Starting camera acquisition")
        self._dropped_frames = 0
        self._pre_frame_time = time.time()
        self._pre_frame_count = 0
        self._cam.cap_start()

    @describe(label="Grab Frame", desc="Grab a single frame from the camera buffer.")
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer."""
        timeout_ms = 1000
        dtype = np.uint8 if self.pixel_format == "MONO8" else np.uint16

        try:
            if self._cam.wait_capevent_frameready(timeout_ms) is not False:
                image = self._cam.buf_getlastframedata()
                if image is not False:
                    self._latest_frame = np.copy(image)
                    return image
        except Exception:
            self.log.exception("Failed to grab frame")

        # Return empty frame on failure
        image = np.zeros((self.frame_size_px.y, self.frame_size_px.x), dtype=dtype)
        self._latest_frame = image
        return image

    @describe(label="Stop", desc="Stop the camera acquisition.")
    def stop(self) -> None:
        """Stop the camera."""
        self.log.info("Stopping camera acquisition")
        self._cam.buf_release()
        self._cam.cap_stop()

    # ==================== Temperature ====================

    @property
    @describe(label="Sensor Temperature", units="°C", desc="Temperature of the sensor.")
    def sensor_temperature_c(self) -> float:
        """Get the sensor temperature in Celsius."""
        return _unwrap(self._cam.prop_getvalue(_PROPS["sensor_temperature"]), 0.0)

    # ==================== Line Interval ====================

    @deliminated_float(
        min_value=lambda self: _unwrap(self._cam.prop_getattr(_PROPS["line_interval"]), _DEFAULT_ATTR).valuemin * 1e6,
        max_value=lambda self: _unwrap(self._cam.prop_getattr(_PROPS["line_interval"]), _DEFAULT_ATTR).valuemax * 1e6,
        step=0.01,
    )
    @describe(label="Line Interval", units="µs", desc="Internal line interval for rolling shutter.")
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds."""
        return _unwrap(self._cam.prop_getvalue(_PROPS["line_interval"]), 0.0) * 1e6

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float) -> None:
        """Set the line interval in microseconds."""
        self._cam.prop_setvalue(_PROPS["line_interval"], line_interval_us / 1e6)
        self.log.debug(f"Line interval set to {line_interval_us} µs")

    # ==================== Lifecycle ====================

    def close(self) -> None:
        """Close the camera connection."""
        self.log.info("Closing Hamamatsu camera")
        if self._dcam and self._dcam.is_opened():
            self._dcam.dev_close()
            _get_dcamapi().uninit()

    # ==================== Internal Methods ====================

    def _query_binning_options(self) -> list[int]:
        """Query available binning options from the camera."""
        available: list[int] = []

        try:
            attr = _unwrap(self._cam.prop_getattr(_PROPS["binning"]), _DEFAULT_ATTR)
            min_val = int(attr.valuemin)
            max_val = int(attr.valuemax)

            for val in range(min_val, max_val + 1):
                text = _unwrap(self._cam.prop_getvaluetext(_PROPS["binning"], val), "")
                if text:
                    available.append(val)
        except Exception:
            self.log.debug("Failed to query binning options")

        return available if available else [1]

    def _query_pixel_format_options(self) -> list[PixelFormat]:
        """Query available pixel format options from the camera."""
        available: list[PixelFormat] = []
        self._pixel_type_map: dict[str, int] = {}

        try:
            attr = _unwrap(self._cam.prop_getattr(_PROPS["pixel_type"]), _DEFAULT_ATTR)
            min_val = int(attr.valuemin)
            max_val = int(attr.valuemax)

            for val in range(min_val, max_val + 1):
                text = _unwrap(self._cam.prop_getvaluetext(_PROPS["pixel_type"], val), "")
                if text:
                    dcam_name = text.lower()
                    self._pixel_type_map[dcam_name] = val
                    if dcam_name in _DCAM_TO_PIXEL_FMT:
                        available.append(_DCAM_TO_PIXEL_FMT[dcam_name])
        except Exception:
            self.log.debug("Failed to query pixel format options")

        return available if available else ["MONO16"]

    def _query_sensor_mode_options(self) -> dict[str, int]:
        """Query available sensor mode options from the camera."""
        options: dict[str, int] = {}

        try:
            attr = _unwrap(self._cam.prop_getattr(_PROPS["sensor_mode"]), _DEFAULT_ATTR)
            min_val = int(attr.valuemin)
            max_val = int(attr.valuemax)

            for val in range(min_val, max_val + 1):
                text = _unwrap(self._cam.prop_getvaluetext(_PROPS["sensor_mode"], val), "")
                if text:
                    options[text.lower()] = val
        except Exception:
            self.log.debug("Failed to query sensor mode options")

        return options if options else {"area": 1}

    def _query_readout_direction_options(self) -> dict[str, int]:
        """Query available readout direction options from the camera."""
        options: dict[str, int] = {}

        try:
            attr = _unwrap(self._cam.prop_getattr(_PROPS["readout_direction"]), _DEFAULT_ATTR)
            min_val = int(attr.valuemin)
            max_val = int(attr.valuemax)

            for val in range(min_val, max_val + 1):
                text = _unwrap(self._cam.prop_getvaluetext(_PROPS["readout_direction"], val), "")
                if text:
                    options[text.lower()] = val
        except Exception:
            self.log.debug("Failed to query readout direction options")

        return options if options else {"forward": 1}

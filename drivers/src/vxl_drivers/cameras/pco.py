"""PCO camera driver using pco SDK."""

from enum import StrEnum

import numpy as np
import pco  # pyright: ignore[reportMissingImports]
from rigup.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string
from vxlib.vec import IVec2D, Vec2D

from rigup import describe
from vxl.camera.base import Camera, FrameRegion, PixelFormat, StreamInfo, TriggerMode, TriggerPolarity

# Buffer size in MB for frame storage
BUFFER_SIZE_MB = 2400

# PCO binning options (subset of standard options)
PCO_BINNING_OPTIONS = [1, 2, 4]


class ReadoutMode(StrEnum):
    """Readout modes for PCO sCMOS cameras."""

    LIGHT_SHEET_FORWARD = "light sheet forward"
    ROLLING_IN = "rolling in"
    ROLLING_OUT = "rolling out"
    ROLLING_UP = "rolling up"
    ROLLING_DOWN = "rolling down"
    LIGHT_SHEET_BACKWARD = "light sheet backward"


# Readout mode to PCO format mapping (string keys for type safety)
_READOUT_MODE_MAP: dict[str, int] = {
    ReadoutMode.LIGHT_SHEET_FORWARD.value: 0,
    ReadoutMode.ROLLING_IN.value: 256,
    ReadoutMode.ROLLING_OUT.value: 512,
    ReadoutMode.ROLLING_UP.value: 768,
    ReadoutMode.ROLLING_DOWN.value: 1024,
    ReadoutMode.LIGHT_SHEET_BACKWARD.value: 1280,
}


class PCOCamera(Camera):
    """PCO camera driver using pco SDK.

    Supports PCO sCMOS cameras including Edge series.
    Note: PCO cameras only support 16-bit pixel format.
    """

    def __init__(
        self,
        uid: str,
        interface: str = "Camera Link Silicon Software",
        pixel_size_um: Vec2D | tuple[float, float] | list[float] | str = (6.5, 6.5),
    ) -> None:
        """Initialize the PCO camera.

        Args:
            uid: Unique identifier for this device.
            interface: Camera interface name (e.g., "Camera Link Silicon Software").
            pixel_size_um: Physical pixel size in microns (y, x). Default is 6.5µm for PCO Edge.
        """
        super().__init__(uid=uid)

        self._interface = interface
        self._pixel_size_um = pixel_size_um if isinstance(pixel_size_um, Vec2D) else Vec2D.parse(pixel_size_um)
        self._latest_frame: np.ndarray | None = None
        self._buffer_size_frames = 0

        # Initialize camera
        self._pco = pco.Camera(interface=interface)

        # Cache sensor dimensions
        desc = self._pco.sdk.get_camera_description()
        self._sensor_width = desc["max. horizontal resolution standard"]
        self._sensor_height = desc["max. vertical resolution standard"]

        # Query available trigger modes
        self._trigger_modes = self._query_trigger_modes()

        self.log.info(
            f"Initialized PCO camera: interface={interface}, sensor={self._sensor_width}x{self._sensor_height}",
        )

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

    @enumerated_string(options=["MONO16"])
    def pixel_format(self) -> PixelFormat:
        """Get the pixel format of the camera.

        Note: PCO cameras only support 16-bit output.
        """
        return "MONO16"

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel format of the camera."""
        if pixel_format != "MONO16":
            self.log.warning("PCO cameras only support MONO16 format")

    # ==================== Binning ====================

    @enumerated_int(options=PCO_BINNING_OPTIONS)
    def binning(self) -> int:
        """Get the binning mode of the camera."""
        return self._pco.sdk.get_binning()["binning x"]

    @binning.setter
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera."""
        if binning not in PCO_BINNING_OPTIONS:
            raise ValueError(f"Invalid binning: {binning}. Valid: {PCO_BINNING_OPTIONS}")
        self._pco.sdk.set_binning(binning, binning)
        self.log.debug(f"Binning set to {binning}x{binning}")

    # ==================== Exposure & Frame Rate ====================

    @deliminated_float(min_value=0.001, max_value=10000.0, step=0.001)
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms."""
        return self._pco.exposure_time * 1000  # s to ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms."""
        self._pco.exposure_time = exposure_time_ms / 1000  # ms to s
        self.log.debug(f"Exposure time set to {exposure_time_ms} ms")

    @deliminated_float(min_value=0.1, max_value=1000.0, step=0.1)
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz."""
        # Estimate from frame time
        frame_time_ms = self._get_frame_time_ms()
        return 1000 / frame_time_ms if frame_time_ms > 0 else 0

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate of the camera in Hz."""
        del value  # unused - frame rate controlled via line timing
        self.log.warning("Frame rate is controlled via line timing on PCO cameras")

    def _get_frame_time_ms(self) -> float:
        """Calculate frame time based on readout mode."""
        line_interval_us = self._pco.sdk.get_cmos_line_timing()["line time"] * 1e6
        region = self.frame_region
        exposure_ms = self.exposure_time_ms

        readout_mode = self._get_readout_mode()
        if "light sheet" in readout_mode:
            return (line_interval_us * int(region.height)) / 1000 + exposure_ms
        return (line_interval_us * int(region.height) / 2) / 1000 + exposure_ms

    # ==================== Frame Region ====================

    @property
    def frame_region(self) -> FrameRegion:
        """Get current frame region with embedded constraints."""
        roi_dict = self._pco.sdk.get_roi()
        desc = self._pco.sdk.get_camera_description()

        # PCO uses 1-based indexing
        x = roi_dict["x0"] - 1
        y = roi_dict["y0"] - 1
        width = roi_dict["x1"] - roi_dict["x0"] + 1
        height = roi_dict["y1"] - roi_dict["y0"] + 1

        step_x = desc.get("roi hor steps", 1)
        step_y = desc.get("roi vert steps", 1)
        min_w = desc.get("min size horz", 32)
        min_h = desc.get("min size vert", 32)

        return FrameRegion(
            x=DeliminatedInt(x, min_value=0, max_value=self._sensor_width - min_w, step=step_x),
            y=DeliminatedInt(y, min_value=0, max_value=self._sensor_height - min_h, step=step_y),
            width=DeliminatedInt(width, min_value=min_w, max_value=self._sensor_width, step=step_x),
            height=DeliminatedInt(height, min_value=min_h, max_value=self._sensor_height, step=step_y),
        )

    def update_frame_region(
        self,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Update frame region. Only provided values are changed."""
        # Get current values for any not being updated
        current = self.frame_region

        new_x = x if x is not None else int(current.x)
        new_y = y if y is not None else int(current.y)
        new_w = width if width is not None else int(current.width)
        new_h = height if height is not None else int(current.height)

        # PCO uses 1-based indexing: x0, y0, x1, y1
        x0 = new_x + 1
        y0 = new_y + 1
        x1 = new_x + new_w
        y1 = new_y + new_h

        self._pco.sdk.set_roi(x0, y0, x1, y1)
        self.log.debug(f"Frame region updated: x={new_x}, y={new_y}, w={new_w}, h={new_h}")

    # ==================== Readout Mode ====================

    @enumerated_string(options=list(ReadoutMode))
    @describe(label="Readout Mode", desc="sCMOS readout direction mode.")
    def readout_mode(self) -> str:
        """Get the readout mode."""
        return self._get_readout_mode()

    @readout_mode.setter
    def readout_mode(self, mode: str) -> None:
        """Set the readout mode."""
        if mode not in _READOUT_MODE_MAP:
            raise ValueError(f"Invalid readout mode: {mode}")
        self._pco.sdk.set_interface_output_format(interface="edge", format=_READOUT_MODE_MAP[mode])
        self.log.debug(f"Readout mode set to {mode}")

    def _get_readout_mode(self) -> str:
        """Get current readout mode string."""
        fmt = self._pco.sdk.get_interface_output_format("edge")["format"]
        for mode, value in _READOUT_MODE_MAP.items():
            if value == fmt:
                return mode
        return ReadoutMode.ROLLING_OUT.value

    # ==================== Stream Info ====================

    @property
    @describe(label="Stream Info", desc="Acquisition state info or None if not streaming.", stream=True)
    def stream_info(self) -> StreamInfo | None:
        """Return acquisition state or None if not acquiring."""
        try:
            status = self._pco.rec.get_status()
            frame_index = status.get("dwProcImgCount", 0)
            dropped_frames = 1 if status.get("bFIFOOverflow", False) else 0

            frame_rate = 1000 / self._get_frame_time_ms() if self._get_frame_time_ms() > 0 else 0
            data_rate = frame_rate * self.frame_size_mb

            return StreamInfo(
                frame_index=frame_index,
                input_buffer_size=self._buffer_size_frames,
                output_buffer_size=0,
                dropped_frames=dropped_frames,
                frame_rate_fps=frame_rate,
                data_rate_mbs=data_rate,
            )
        except Exception:
            return None

    # ==================== Trigger Configuration ====================

    def _configure_trigger_mode(self, mode: TriggerMode) -> None:
        """Configure the trigger mode of the camera."""
        if mode == TriggerMode.ON:
            self._pco.sdk.set_trigger_mode(mode="external exposure start & software trigger")
            self._pco.sdk.set_acquire_mode(mode="external")
        else:
            self._pco.sdk.set_trigger_mode(mode="auto trigger")
            self._pco.sdk.set_acquire_mode(mode="auto")
        self.log.debug(f"Trigger mode set to {mode}")

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        """Configure the trigger polarity of the camera."""
        # PCO trigger polarity is typically fixed
        self.log.debug(f"Trigger polarity {polarity} (PCO polarity is hardware-defined)")

    # ==================== Acquisition ====================

    def _prepare_for_capture(self) -> None:
        """Prepare the camera to acquire images."""
        # PCO uses 16-bit (2 bytes per pixel)
        frame_size_mb = self.frame_size_px.x * self.frame_size_px.y * 2 / (1024**2)
        self._buffer_size_frames = round(BUFFER_SIZE_MB / frame_size_mb)
        self._pco.record(number_of_images=self._buffer_size_frames, mode="fifo")
        self.log.debug(f"Buffer set to {self._buffer_size_frames} frames")

    @describe(label="Start", desc="Start acquiring frames from the camera.")
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire frames.

        Note: PCO cameras start recording when record() is called in _prepare_for_capture().
        This method is a no-op since acquisition is already running.
        """
        del frame_count  # unused - continuous acquisition
        self.log.info("Camera acquisition already started via record()")

    @describe(label="Grab Frame", desc="Grab a single frame from the camera buffer.")
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer."""
        try:
            self._pco.wait_for_new_image(delay=True, timeout=1)
            image, _metadata = self._pco.image(image_index=0)
        except Exception:
            self.log.exception("Failed to grab frame")
            image = np.zeros((self.frame_size_px.y, self.frame_size_px.x), dtype=np.uint16)

        self._latest_frame = np.copy(image)
        return image

    @describe(label="Stop", desc="Stop the camera acquisition.")
    def stop(self) -> None:
        """Stop the camera."""
        self.log.info("Stopping camera acquisition")
        self._pco.stop()

    # ==================== Temperature ====================

    @property
    @describe(label="Camera Temperature", units="°C", desc="Temperature of the camera.")
    def camera_temperature_c(self) -> float:
        """Get the camera temperature in Celsius."""
        return self._pco.sdk.get_temperature()["camera temperature"]

    @property
    @describe(label="Sensor Temperature", units="°C", desc="Temperature of the sensor.")
    def sensor_temperature_c(self) -> float:
        """Get the sensor temperature in Celsius."""
        return self._pco.sdk.get_temperature()["sensor temperature"]

    # ==================== Line Timing ====================

    @deliminated_float(min_value=1.0, max_value=1000.0, step=0.1)
    @describe(label="Line Interval", units="µs", desc="Line interval for rolling shutter.")
    def line_interval_us(self) -> float:
        """Get the line interval in microseconds."""
        return self._pco.sdk.get_cmos_line_timing()["line time"] * 1e6

    @line_interval_us.setter
    def line_interval_us(self, line_interval_us: float) -> None:
        """Set the line interval in microseconds."""
        self._pco.sdk.set_cmos_line_timing("on", line_interval_us / 1e6)
        self.log.debug(f"Line interval set to {line_interval_us} µs")

    # ==================== Lifecycle ====================

    def close(self) -> None:
        """Close the camera connection."""
        self.log.info("Closing PCO camera")
        self._pco.close()

    # ==================== Internal Methods ====================

    def _query_trigger_modes(self) -> dict[str, str]:
        """Query available trigger modes from the camera."""
        modes = {}
        try:
            desc = self._pco.sdk.get_camera_description()
            # Parse trigger mode capabilities from description
            # GENERALCAPS1_NO_EXTEXPCTRL = 0x00000080 means NO external exposure control
            if not (desc.get("dwGeneralCapsDESC1", 0) & 0x00000080):
                modes["external"] = "external exposure start & software trigger"
            modes["auto"] = "auto trigger"
        except Exception:
            modes["auto"] = "auto trigger"
        return modes

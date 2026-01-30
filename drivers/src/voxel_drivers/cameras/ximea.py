"""Ximea camera driver using xiapi SDK."""

import re
from contextlib import suppress
from typing import Any

import numpy as np
from pyrig.device.props import DeliminatedInt, deliminated_float, enumerated_int, enumerated_string
from vxlib.vec import IVec2D, Vec2D
from ximea_python import xiapi
from ximea_python.xidefs import XI_BIT_DEPTH, XI_DOWNSAMPLING_VALUE

from pyrig import describe
from vxl.camera.base import (
    Camera,
    FrameRegion,
    PixelFormat,
    StreamInfo,
    TriggerMode,
    TriggerPolarity,
)


def _to_int(value: Any) -> int:
    """Convert xiapi return value to int, defaulting to 0 if None."""
    return int(value) if value is not None else 0


def _to_float(value: Any) -> float:
    """Convert xiapi return value to float, defaulting to 0.0 if None."""
    return float(value) if value is not None else 0.0


def _to_str(value: Any) -> str:
    """Convert xiapi return value to str, defaulting to empty string if None."""
    return str(value) if value is not None else ""


# Buffer size in MB for frame storage
BUFFER_SIZE_MB = 2400

# Pixel format mapping: Ximea format -> Camera format
_XIMEA_TO_PIXEL_FMT: dict[str, PixelFormat] = {
    "XI_BPP_8": "MONO8",
    "XI_BPP_10": "MONO10",
    "XI_BPP_12": "MONO12",
    "XI_BPP_14": "MONO14",
    "XI_BPP_16": "MONO16",
}

_PIXEL_FMT_TO_XIMEA: dict[PixelFormat, str] = {v: k for k, v in _XIMEA_TO_PIXEL_FMT.items()}


class XimeaCamera(Camera):
    """Ximea camera driver using xiapi SDK.

    Supports Ximea cameras with various sensor types including Sony IMX sensors.
    """

    def __init__(
        self,
        uid: str,
        serial: str,
        pixel_size_um: Vec2D | tuple[float, float] | list[float] | str = (1.0, 1.0),
    ) -> None:
        """Initialize the Ximea camera.

        Args:
            uid: Unique identifier for this device.
            serial: Camera serial number.
            pixel_size_um: Physical pixel size in microns (y, x).
        """
        super().__init__(uid=uid)

        self._serial = str(serial)
        self._pixel_size_um = pixel_size_um if isinstance(pixel_size_um, Vec2D) else Vec2D.parse(pixel_size_um)
        self._latest_frame: np.ndarray | None = None
        self._buffer_size_frames = 0

        # Initialize camera
        self._camera = xiapi.Camera()
        self._camera.open_device_by_SN(self._serial)
        self._image = xiapi.Image()

        # Disable BW limit to not influence sensor line period
        self._camera.set_limit_bandwidth_mode("XI_OFF")

        # Cache sensor dimensions
        self._sensor_width: int = _to_int(self._camera.get_width_maximum())
        self._sensor_height: int = _to_int(self._camera.get_height_maximum())

        # Query available options from driver
        self._available_pixel_formats = self._query_pixel_formats()
        self._binning_options = self._query_binning_options()

        self.log.info(f"Initialized Ximea camera: serial={serial}, sensor={self._sensor_width}x{self._sensor_height}")

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

    @enumerated_string(options=list(_PIXEL_FMT_TO_XIMEA.keys()))
    def pixel_format(self) -> PixelFormat:
        """Get the pixel format of the camera."""
        ximea_fmt: str = _to_str(self._camera.get_output_bit_depth())
        return _XIMEA_TO_PIXEL_FMT.get(ximea_fmt.upper(), "MONO16")

    @pixel_format.setter
    def pixel_format(self, pixel_format: str) -> None:
        """Set the pixel format of the camera."""
        if pixel_format not in _PIXEL_FMT_TO_XIMEA:
            raise ValueError(f"Invalid pixel format: {pixel_format}. Valid: {list(_PIXEL_FMT_TO_XIMEA.keys())}")

        ximea_fmt = _PIXEL_FMT_TO_XIMEA[pixel_format]
        self._camera.set_output_bit_depth(ximea_fmt)
        self._camera.set_sensor_bit_depth(ximea_fmt)

        # Set image data format based on bit depth
        if pixel_format == "MONO8":
            self._camera.set_imgdataformat("XI_MONO8")
        else:
            self._camera.set_imgdataformat("XI_MONO16")

        self.log.debug(f"Pixel format set to {pixel_format}")

    # ==================== Binning ====================

    @enumerated_int(options=lambda self: self._binning_options)
    def binning(self) -> int:
        """Get the binning mode of the camera."""
        raw: str = _to_str(self._camera.get_downsampling())
        return self._parse_binning_str(raw)

    @binning.setter
    def binning(self, binning: int) -> None:
        """Set the binning mode of the camera."""
        if binning not in self._binning_options:
            raise ValueError(f"Invalid binning: {binning}. Valid: {self._binning_options}")

        binning_str = f"XI_DWN_{binning}x{binning}"
        self._camera.set_downsampling(binning_str)
        self.log.debug(f"Binning set to {binning}x{binning}")

    # ==================== Exposure & Frame Rate ====================

    @deliminated_float(
        min_value=lambda self: _to_float(self._camera.get_exposure_minimum()) / 1000,
        max_value=lambda self: _to_float(self._camera.get_exposure_maximum()) / 1000,
        step=0.001,
    )
    def exposure_time_ms(self) -> float:
        """Get the exposure time of the camera in ms."""
        return _to_float(self._camera.get_exposure()) / 1000  # us to ms

    @exposure_time_ms.setter
    def exposure_time_ms(self, exposure_time_ms: float) -> None:
        """Set the exposure time of the camera in ms."""
        self._camera.set_exposure(round(exposure_time_ms * 1000, 1))  # ms to us
        self.log.debug(f"Exposure time set to {exposure_time_ms} ms")

    @deliminated_float(min_value=0.1, max_value=1000.0, step=0.1)
    def frame_rate_hz(self) -> float:
        """Get the frame rate of the camera in Hz."""
        return _to_float(self._camera.get_framerate())

    @frame_rate_hz.setter
    def frame_rate_hz(self, value: float) -> None:
        """Set the frame rate of the camera in Hz."""
        del value  # unused - frame rate controlled via exposure time
        self.log.warning("Frame rate is controlled via exposure time on Ximea cameras")

    # ==================== Frame Region ====================

    @property
    def frame_region(self) -> FrameRegion:
        """Get current frame region with embedded constraints."""
        return FrameRegion(
            x=DeliminatedInt(
                _to_int(self._camera.get_offsetX()),
                min_value=0,
                max_value=self._sensor_width - _to_int(self._camera.get_width_minimum()),
                step=_to_int(self._camera.get_width_increment()),
            ),
            y=DeliminatedInt(
                _to_int(self._camera.get_offsetY()),
                min_value=0,
                max_value=self._sensor_height - _to_int(self._camera.get_height_minimum()),
                step=_to_int(self._camera.get_height_increment()),
            ),
            width=DeliminatedInt(
                _to_int(self._camera.get_width()),
                min_value=_to_int(self._camera.get_width_minimum()),
                max_value=self._sensor_width,
                step=_to_int(self._camera.get_width_increment()),
            ),
            height=DeliminatedInt(
                _to_int(self._camera.get_height()),
                min_value=_to_int(self._camera.get_height_minimum()),
                max_value=self._sensor_height,
                step=_to_int(self._camera.get_height_increment()),
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
        # Reset offsets first to allow full width/height adjustment
        if width is not None or height is not None:
            self._camera.set_offsetX(0)
            self._camera.set_offsetY(0)

        # Set dimensions
        if width is not None:
            self._camera.set_width(width)
        if height is not None:
            self._camera.set_height(height)

        # Set offsets
        if x is not None:
            self._camera.set_offsetX(x)
        if y is not None:
            self._camera.set_offsetY(y)

        self.log.debug(f"Frame region updated: x={x}, y={y}, w={width}, h={height}")

    # ==================== Stream Info ====================

    @property
    @describe(label="Stream Info", desc="Acquisition state info or None if not streaming.", stream=True)
    def stream_info(self) -> StreamInfo | None:
        """Return acquisition state or None if not acquiring."""
        try:
            self._camera.set_counter_selector("XI_CNT_SEL_TRANSPORT_TRANSFERRED_FRAMES")
            frame_index = _to_int(self._camera.get_counter_value())

            self._camera.set_counter_selector("XI_CNT_SEL_API_SKIPPED_FRAMES")
            dropped_frames = _to_int(self._camera.get_counter_value())

            frame_rate = _to_float(self._camera.get_framerate())
            data_rate = frame_rate * self.frame_size_mb

            return StreamInfo(
                frame_index=frame_index,
                input_buffer_size=self._buffer_size_frames,
                output_buffer_size=0,  # Not available in xiapi
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
            self._camera.set_trigger_source("XI_TRG_EDGE_RISING")
        else:
            self._camera.set_trigger_source("XI_TRG_OFF")
        self.log.debug(f"Trigger mode set to {mode}")

    def _configure_trigger_polarity(self, polarity: TriggerPolarity) -> None:
        """Configure the trigger polarity of the camera."""
        if polarity == TriggerPolarity.RISING_EDGE:
            self._camera.set_trigger_source("XI_TRG_EDGE_RISING")
        else:
            self._camera.set_trigger_source("XI_TRG_EDGE_FALLING")
        self.log.debug(f"Trigger polarity set to {polarity}")

    # ==================== Acquisition ====================

    def _prepare_for_capture(self) -> None:
        """Prepare the camera to acquire images."""
        self._buffer_size_frames = round(BUFFER_SIZE_MB / self.frame_size_mb)
        self._camera.set_acq_buffer_size_unit(1024**2)  # Buffer size in MB
        self._camera.set_acq_buffer_size(int(self._buffer_size_frames * self.frame_size_mb))
        self.log.debug(f"Buffer set to {self._buffer_size_frames} frames")

    @describe(label="Start", desc="Start acquiring frames from the camera.")
    def start(self, frame_count: int | None = None) -> None:
        """Start the camera to acquire frames."""
        del frame_count  # unused - continuous acquisition
        self.log.info("Starting camera acquisition")
        self._camera.start_acquisition()

    @describe(label="Grab Frame", desc="Grab a single frame from the camera buffer.")
    def grab_frame(self) -> np.ndarray:
        """Grab a frame from the camera buffer."""
        try:
            self._camera.get_image(self._image)
            image = self._image.get_image_data_numpy()
        except Exception:
            self.log.exception("Failed to grab frame")
            dtype = np.uint8 if self.pixel_format == "MONO8" else np.uint16
            image = np.zeros((self.frame_size_px.y, self.frame_size_px.x), dtype=dtype)

        self._latest_frame = np.copy(image)
        return image

    @describe(label="Stop", desc="Stop the camera acquisition.")
    def stop(self) -> None:
        """Stop the camera."""
        self.log.info("Stopping camera acquisition")
        self._camera.stop_acquisition()

    # ==================== Temperature ====================

    @property
    @describe(label="Sensor Temperature", units="°C", desc="Temperature of the sensor board.")
    def sensor_temperature_c(self) -> float:
        """Get the sensor temperature in Celsius."""
        self._camera.set_temp_selector("XI_TEMP_SENSOR_BOARD")
        return _to_float(self._camera.get_temp())

    @property
    @describe(label="Interface Temperature", units="°C", desc="Temperature of the interface board.")
    def interface_temperature_c(self) -> float:
        """Get the interface board temperature in Celsius."""
        self._camera.set_temp_selector("XI_TEMP_INTERFACE_BOARD")
        return _to_float(self._camera.get_temp())

    # ==================== Lifecycle ====================

    def close(self) -> None:
        """Close the camera connection."""
        self.log.info("Closing Ximea camera")
        self._camera.close_device()

    # ==================== Internal Methods ====================

    def _query_pixel_formats(self) -> list[PixelFormat]:
        """Query available pixel formats from the camera."""
        available: list[PixelFormat] = []
        init_depth = self._camera.get_sensor_bit_depth()

        for depth in XI_BIT_DEPTH:
            with suppress(Exception):
                self._camera.set_sensor_bit_depth(depth)
                if depth in _XIMEA_TO_PIXEL_FMT:
                    available.append(_XIMEA_TO_PIXEL_FMT[depth])

        self._camera.set_sensor_bit_depth(init_depth)
        return available

    def _query_binning_options(self) -> list[int]:
        """Query available binning options from the camera.

        Iterates through XI_DOWNSAMPLING_VALUE options, tries to set each,
        and keeps only the ones that work. Defaults to [1] if none found.
        """
        available: list[int] = []
        init_binning = self._camera.get_downsampling()

        for binning_str in XI_DOWNSAMPLING_VALUE:
            try:
                self._camera.set_downsampling(binning_str)
                binning_val = self._parse_binning_str(binning_str)
                available.append(binning_val)
            except Exception:
                self.log.debug(f"Binning {binning_str} not available on this camera")

        # Restore initial value
        with suppress(Exception):
            self._camera.set_downsampling(init_binning)

        # Default to [1] if no options found
        if not available:
            available = [1]
            self.log.warning("No binning options found, defaulting to [1]")

        return sorted(set(available))

    @staticmethod
    def _parse_binning_str(binning_str: str) -> int:
        """Parse Ximea binning string to integer.

        Args:
            binning_str: String like "XI_DWN_1x1", "XI_DWN_2x2", etc.

        Returns:
            Integer binning value (e.g., 1, 2, 4).
        """
        # Format: XI_DWN_NxN -> extract N
        match = re.search(r"(\d+)x\d+", binning_str)
        if match:
            return int(match.group(1))
        return 1

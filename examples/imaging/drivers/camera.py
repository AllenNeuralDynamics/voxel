from pathlib import Path

import zmq.asyncio

from pyrig import DeviceHandle
from pyrig.cluster import DeviceAddress, DeviceService
from pyrig.device import Adapter, Device, describe


def parse_tuple_str(str: str) -> tuple[float, float]:
    try:
        x, y = map(float, str.split(","))
        return x, y
    except ValueError:
        raise ValueError("Invalid tuple string format")


class Camera(Device):
    """A mock camera device for testing property and command interfaces."""

    __DEVICE_TYPE__ = "camera"

    def __init__(self, uid: str, pixel_size_um: str):
        super().__init__(uid=uid)
        self._pixel_size = parse_tuple_str(pixel_size_um)
        self._exposure_time: float = 0.0

    @property
    @describe(label="Pixel Size", units="um")
    def pixel_size(self) -> tuple[float, float]:
        """Get the pixel size."""
        return self._pixel_size

    @property
    @describe(label="Frame Time", units="ms")
    def frame_time(self) -> float:
        """Get the frame time in milliseconds."""
        return self._exposure_time * 1.1

    @property
    @describe(label="Exposure Time", units="ms")
    def exposure_time(self) -> float:
        """Get the exposure time in milliseconds."""
        return self._exposure_time

    @exposure_time.setter
    def exposure_time(self, value: float) -> None:
        """Set the exposure time in milliseconds."""
        if value < 0:
            raise ValueError("Exposure time must be non-negative")
        if value > 100:
            raise ValueError("Exposure time cannot exceed 100")
        if value != self._exposure_time:
            self.log.info("exposure_time updated: %.1f -> %.1f ms", self._exposure_time, value)
        self._exposure_time = value


class Writer:
    """Simple file writer for camera data."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def write(self, text: str) -> None:
        """Append data to the file."""
        with self.file_path.open("a") as f:
            f.write(text)


class CameraService(DeviceService[Camera]):
    """Camera service with extended streaming commands."""

    def __init__(self, device: Camera, conn: DeviceAddress, zctx: zmq.asyncio.Context):
        super().__init__(device, conn, zctx)
        tmp_folder = Path(__file__).parent.parent / "tmp"
        tmp_folder.mkdir(exist_ok=True)
        self._writer = Writer(str(tmp_folder / f"{device.uid}.txt"))

    @describe(label="Start Stream", desc="Start streaming frames to file")
    def start_stream(self, num_frames: int = 10) -> str:
        """Start streaming frames."""
        self.log.info("Starting stream: %d frames -> %s", num_frames, self._writer.file_path.name)
        self._writer.write(f"Starting stream with {num_frames} frames\n")
        for i in range(num_frames):
            self._writer.write(f"Frame {i + 1}\n")
        self._writer.write("Stream complete\n")
        self.log.info("Stream complete: %d frames written", num_frames)
        return f"Streamed {num_frames} frames to {self._writer.file_path.name}"


class CameraHandle(DeviceHandle[Camera]):
    """Typed handle for Camera devices with streaming support."""

    def __init__(self, adapter: Adapter[Camera]):
        super().__init__(adapter)

    async def get_exposure_time(self) -> float:
        """Get the camera exposure time in milliseconds."""
        return await self.get_prop_value("exposure_time")

    async def set_exposure_time(self, value: float) -> None:
        """Set the camera exposure time in milliseconds."""
        await self.set_prop("exposure_time", value)

    async def get_pixel_size(self) -> tuple[float, float]:
        """Get the pixel size in micrometers."""
        return await self.get_prop_value("pixel_size")

    async def get_frame_time(self) -> float:
        """Get the frame time in milliseconds."""
        return await self.get_prop_value("frame_time")

    async def start_stream(self, num_frames: int = 10) -> str:
        """Start streaming frames (service-level command)."""
        return await self.call("start_stream", num_frames)

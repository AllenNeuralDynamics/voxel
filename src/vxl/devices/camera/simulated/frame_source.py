import gzip
import hashlib
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Self
from urllib.request import Request, urlopen

import cv2
import numpy as np
from pydantic import Field, TypeAdapter, model_validator
from vxlib.schema import FrozenModel, SparseModel
from vxlib.vector import IVec2D, Vec2D

from vxl.devices.camera.base import SensorROI, ValidBits
from vxl.system import System

DEFAULT_REFERENCE_PATH = Path(__file__).with_name("default_reference.png")
DEFAULT_SENSOR_SIZE_PX = IVec2D(y=10_640, x=14_192)
DEFAULT_PIXEL_SIZE_UM = Vec2D(y=1.0, x=1.0)

type PatternName = Literal["checkerboard", "gradient_x", "gradient_y"]


class _Readable(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


class _Writable(Protocol):
    def write(self, data: bytes, /) -> int: ...


@dataclass(frozen=True)
class _Asset:
    url: str
    compressed_size: int
    sha256: str
    frame_size: int
    shape: tuple[int, int]
    dtype: Literal["uint16"]
    pixel_size_um: Vec2D
    source_valid_bits: ValidBits


_ASSETS: dict[str, _Asset] = {
    "exaspim-786399-tile-000001-ch-488-z-10496-v1": _Asset(
        url=(
            "https://github.com/waltermwaniki/voxel-wheels/releases/download/simulated-camera-v1/"
            "exaspim-786399-tile-000001-ch-488-z-10496-v1.npy.gz"
        ),
        compressed_size=108_923_729,
        sha256="0120a295d9f2bcee51000012d40745540bf1f8867f2b2a25dae0611c25f5d9a7",
        frame_size=302_005_888,
        shape=(10_640, 14_192),
        dtype="uint16",
        pixel_size_um=Vec2D(y=3.76, x=3.76),
        source_valid_bits=16,
    ),
    "exaspim-786399-tile-000004-ch-488-z-7488-v1": _Asset(
        url=(
            "https://github.com/waltermwaniki/voxel-wheels/releases/download/simulated-camera-v1/"
            "exaspim-786399-tile-000004-ch-488-z-7488-v1.npy.gz"
        ),
        compressed_size=109_312_967,
        sha256="5de5ef3927b31e1dc29219377c020e77ce20d40027975c7bc1dc21154ad2507f",
        frame_size=302_005_888,
        shape=(10_640, 14_192),
        dtype="uint16",
        pixel_size_um=Vec2D(y=3.76, x=3.76),
        source_valid_bits=16,
    ),
}


class FileFrameSourceConfig(FrozenModel):
    """A local or downloadable 2D image mapped onto a virtual camera sensor."""

    path: Path | None = None
    asset: str | None = Field(default=None, min_length=1)
    sensor_size_px: IVec2D | None = None
    pixel_size_um: Vec2D | None = None
    source_valid_bits: ValidBits | None = None

    @model_validator(mode="after")
    def _validate_metadata(self) -> Self:
        if self.path is not None and self.asset is not None:
            raise ValueError("Specify either path or asset, not both")
        _validate_sensor_metadata(self.sensor_size_px, self.pixel_size_um or DEFAULT_PIXEL_SIZE_UM)
        return self


class PatternFrameSourceConfig(FrozenModel):
    """A deterministic mathematical pattern rendered in sensor coordinates."""

    pattern: PatternName
    sensor_size_px: IVec2D
    pixel_size_um: Vec2D = DEFAULT_PIXEL_SIZE_UM
    source_valid_bits: ValidBits = 16
    tile_size_px: int = Field(default=64, ge=1)

    @model_validator(mode="after")
    def _validate_sensor(self) -> Self:
        _validate_sensor_metadata(self.sensor_size_px, self.pixel_size_um)
        return self


type FrameSourceConfig = FileFrameSourceConfig | PatternFrameSourceConfig

_FRAME_SOURCE_CONFIG_ADAPTER = TypeAdapter(FrameSourceConfig)


class FrameSampleManifest(SparseModel):
    """Provenance and encoding metadata accompanying one exported 2D frame."""

    schema_version: Literal[2] = 2
    source_valid_bits: ValidBits
    source_url: str = Field(min_length=1)
    selected_z: int = Field(ge=0)
    name: str | None = None
    acquisition_id: str | None = None


class FrameSource(ABC):
    """One immutable 2D frame source projected into simulated sensor coordinates."""

    sensor_size_px: IVec2D
    pixel_size_um: Vec2D
    source_valid_bits: ValidBits

    @abstractmethod
    def prepare(self, roi: SensorROI, binning: int) -> np.ndarray:
        """Return source-encoded pixels for the requested sensor ROI and binning."""

    def close(self) -> None:
        """Release source resources."""
        return


class FileFrameSource(FrameSource):
    """A `.npy` or grayscale image file used as an exact or tiled sensor frame."""

    def __init__(self, config: FileFrameSourceConfig) -> None:
        path = config.path or DEFAULT_REFERENCE_PATH
        pixel_size_um = config.pixel_size_um or DEFAULT_PIXEL_SIZE_UM
        source_valid_bits = config.source_valid_bits
        if config.asset is not None:
            path, asset = _resolve_asset(config.asset)
            pixel_size_um = config.pixel_size_um or asset.pixel_size_um
            source_valid_bits = config.source_valid_bits or asset.source_valid_bits
        try:
            self.path = path.expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"Frame source file does not exist: {path.expanduser()}") from exc
        if not self.path.is_file():
            raise ValueError(f"Frame source path is not a file: {self.path}")

        self._frame = _load_frame(self.path)
        self.sensor_size_px = config.sensor_size_px or IVec2D(y=self._frame.shape[0], x=self._frame.shape[1])
        self._tile = (self.sensor_size_px.y, self.sensor_size_px.x) != self._frame.shape
        self.pixel_size_um = pixel_size_um
        try:
            self.source_valid_bits = _resolve_valid_bits(
                source_valid_bits,
                _load_manifest(self.path),
                self._frame.dtype,
            )
        except Exception:
            self.close()
            raise

    def prepare(self, roi: SensorROI, binning: int) -> np.ndarray:
        _validate_geometry(roi, binning, self.sensor_size_px)
        if not self._tile:
            frame = self._frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]
        else:
            source_y = np.arange(roi.y, roi.y + roi.h) % self._frame.shape[0]
            source_x = np.arange(roi.x, roi.x + roi.w) % self._frame.shape[1]
            frame = self._frame[np.ix_(source_y, source_x)]
        return _bin_frame(frame, binning)

    def close(self) -> None:
        frame = getattr(self, "_frame", None)
        self._frame = np.empty((0, 0), dtype=np.uint8)
        if isinstance(frame, np.ndarray):
            _close_array(frame)


class PatternFrameSource(FrameSource):
    """A deterministic pattern evaluated in global sensor coordinates."""

    def __init__(self, config: PatternFrameSourceConfig) -> None:
        self._pattern = config.pattern
        self._tile_size_px = config.tile_size_px
        self.sensor_size_px = config.sensor_size_px
        self.pixel_size_um = config.pixel_size_um
        self.source_valid_bits = config.source_valid_bits

    def prepare(self, roi: SensorROI, binning: int) -> np.ndarray:
        _validate_geometry(roi, binning, self.sensor_size_px)
        y = np.arange(roi.y, roi.y + roi.h, dtype=np.uint64)[:, None]
        x = np.arange(roi.x, roi.x + roi.w, dtype=np.uint64)[None, :]
        maximum = (1 << self.source_valid_bits) - 1
        if self._pattern == "checkerboard":
            frame = ((y // self._tile_size_px + x // self._tile_size_px) % 2) * maximum
        elif self._pattern == "gradient_x":
            line = x * maximum // max(1, self.sensor_size_px.x - 1)
            frame = np.broadcast_to(line, (roi.h, roi.w))
        else:
            line = y * maximum // max(1, self.sensor_size_px.y - 1)
            frame = np.broadcast_to(line, (roi.h, roi.w))
        dtype = np.uint8 if self.source_valid_bits == 8 else np.uint16
        return _bin_frame(frame.astype(dtype), binning)


def create_frame_source(
    config: FrameSource | FrameSourceConfig | Mapping[str, object] | None,
) -> FrameSource:
    if isinstance(config, FrameSource):
        return config
    if config is None:
        parsed: FrameSourceConfig = FileFrameSourceConfig(
            sensor_size_px=DEFAULT_SENSOR_SIZE_PX,
        )
    else:
        parsed = _FRAME_SOURCE_CONFIG_ADAPTER.validate_python(config)
    if isinstance(parsed, FileFrameSourceConfig):
        return FileFrameSource(parsed)
    return PatternFrameSource(parsed)


def _resolve_asset(asset_id: str) -> tuple[Path, _Asset]:
    try:
        asset = _ASSETS[asset_id]
    except KeyError as exc:
        raise ValueError(f"Unknown simulated-camera asset {asset_id!r}; available: {', '.join(_ASSETS)}") from exc

    asset_dir = System().dir / "assets" / "simulated-camera" / asset_id
    frame_path = asset_dir / "frame.npy"
    if not frame_path.is_file() or frame_path.stat().st_size != asset.frame_size:
        asset_dir.mkdir(parents=True, exist_ok=True)
        _download_asset(asset, frame_path)
    return frame_path, asset


def _download_asset(asset: _Asset, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix=".download-", dir=destination.parent) as temporary_value:
        temporary = Path(temporary_value)
        archive_path = temporary / "frame.npy.gz"
        frame_path = temporary / "frame.npy"
        request = Request(  # noqa: S310 - all asset URLs are pinned above and use HTTPS
            asset.url,
            headers={"Accept-Encoding": "identity", "User-Agent": "voxel-simulated-camera-assets/1"},
        )
        try:
            with (
                urlopen(request, timeout=30) as source,  # noqa: S310 - pinned HTTPS URL
                archive_path.open("xb") as target,
            ):
                size, digest = _copy_and_hash(source, target, maximum_size=asset.compressed_size)
        except Exception as exc:
            raise RuntimeError(f"Unable to download simulated-camera asset from {asset.url}: {exc}") from exc
        if size != asset.compressed_size or digest != asset.sha256:
            raise RuntimeError(f"Downloaded simulated-camera asset failed its checksum: {asset.url}")

        with gzip.open(archive_path, "rb") as source, frame_path.open("xb") as target:
            size, _ = _copy_and_hash(source, target, maximum_size=asset.frame_size)
        if size != asset.frame_size:
            raise RuntimeError(f"Decompressed simulated-camera asset has {size} bytes; expected {asset.frame_size}")
        _validate_asset_frame(asset, frame_path)
        frame_path.replace(destination)


def _copy_and_hash(source: _Readable, destination: _Writable, *, maximum_size: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        if size > maximum_size:
            raise RuntimeError(f"Simulated-camera asset exceeds its expected size of {maximum_size} bytes")
        digest.update(chunk)
        destination.write(chunk)
    return size, digest.hexdigest()


def _validate_asset_frame(asset: _Asset, path: Path) -> None:
    try:
        frame = np.load(path, mmap_mode="r", allow_pickle=False)
    except Exception as exc:
        raise RuntimeError(f"Downloaded asset is not a valid NPY frame: {exc}") from exc
    try:
        if frame.shape != asset.shape or frame.dtype != np.dtype(asset.dtype):
            raise RuntimeError(f"Downloaded frame is {frame.shape} {frame.dtype}; expected {asset.shape} {asset.dtype}")
    finally:
        _close_array(frame)


def _load_frame(path: Path) -> np.ndarray:
    match path.suffix.lower():
        case ".npy":
            loaded = np.load(path, mmap_mode="r", allow_pickle=False)
            if not isinstance(loaded, np.ndarray):
                raise ValueError(f"Expected an array in {path}")
            frame = loaded
        case ".png" | ".tif" | ".tiff":
            frame = cv2.imread(str(path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
            if frame is None:
                raise ValueError(f"Unable to read image frame {path}")
        case suffix:
            raise ValueError(f"Unsupported frame source file type {suffix!r}: {path}")
    if frame.ndim != 2:
        _close_array(frame)
        raise ValueError(f"Frame source must contain one 2D image, got shape {frame.shape}: {path}")
    if frame.dtype not in (np.dtype(np.uint8), np.dtype(np.uint16)):
        _close_array(frame)
        raise ValueError(f"Frame source dtype must be uint8 or uint16, got {frame.dtype}: {path}")
    return frame


def _load_manifest(path: Path) -> FrameSampleManifest | None:
    manifest_path = path.with_suffix(".json")
    if not manifest_path.is_file():
        return None
    try:
        return FrameSampleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid frame source manifest {manifest_path}: {exc}") from exc


def _valid_bits_for_storage(storage_bits: int) -> ValidBits:
    if storage_bits == 8:
        return 8
    if storage_bits == 16:
        return 16
    raise ValueError(f"Unsupported frame source storage width: {storage_bits}")


def _resolve_valid_bits(
    configured_bits: ValidBits | None,
    manifest: FrameSampleManifest | None,
    dtype: np.dtype,
) -> ValidBits:
    manifest_bits = manifest.source_valid_bits if manifest is not None else None
    if configured_bits is not None and manifest_bits is not None and configured_bits != manifest_bits:
        raise ValueError(
            f"Configured source_valid_bits={configured_bits} does not match manifest source_valid_bits={manifest_bits}"
        )
    storage_bits = dtype.itemsize * 8
    valid_bits = configured_bits or manifest_bits or _valid_bits_for_storage(storage_bits)
    if valid_bits > storage_bits:
        raise ValueError(f"{valid_bits} valid bits do not fit in {storage_bits}-bit {dtype}")
    return valid_bits


def _close_array(frame: np.ndarray) -> None:
    if isinstance(frame, np.memmap):
        mapping = getattr(frame, "_mmap", None)
        if mapping is not None:
            mapping.close()


def _validate_sensor_metadata(sensor_size: IVec2D | None, pixel_size: Vec2D) -> None:
    if sensor_size is not None and (sensor_size.y <= 0 or sensor_size.x <= 0):
        raise ValueError(f"sensor_size_px must be positive, got {sensor_size}")
    if pixel_size.y <= 0 or pixel_size.x <= 0:
        raise ValueError(f"pixel_size_um must be positive, got {pixel_size}")


def _validate_geometry(roi: SensorROI, binning: int, sensor_size: IVec2D) -> None:
    if roi.x < 0 or roi.y < 0 or roi.x + roi.w > sensor_size.x or roi.y + roi.h > sensor_size.y:
        raise ValueError(f"ROI {roi} exceeds sensor size {sensor_size}")
    if roi.h % binning or roi.w % binning:
        raise ValueError(f"ROI {(roi.h, roi.w)} is not divisible by {binning}x binning")


def _bin_frame(frame: np.ndarray, binning: int) -> np.ndarray:
    if binning == 1:
        return frame
    height, width = frame.shape
    mean = frame.reshape(height // binning, binning, width // binning, binning).sum(axis=(1, 3), dtype=np.uint64) // (
        binning * binning
    )
    return mean.astype(frame.dtype, copy=False)

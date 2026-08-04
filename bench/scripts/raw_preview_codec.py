"""Benchmark raw preview compression on real exaSPIM frames.

This compares the proposed byte-plane shuffle + Zstandard representation with the current preview JPEG-Q95
path. Network reads and the common preview downsample are excluded from codec timings. Each selected catalog
entry contributes its center plane; the full-resolution plane is discarded after its preview sizes are measured.

Examples:
    uv run -m bench.scripts.raw_preview_codec
    uv run -m bench.scripts.raw_preview_codec --catalog-indexes 0 --widths 1024,2048 --repetitions 100
    uv run -m bench.scripts.raw_preview_codec --json-output /tmp/raw-preview-codecs.json
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from numcodecs import Zstd
from rich.console import Console
from rich.table import Table

from bench.data import CATALOG, open_full_res
from vxl.camera.preview import PreviewFrame, PreviewLayer, PreviewViewport

DEFAULT_CATALOG_INDEXES = (0, 1, 2)
DEFAULT_TARGET_WIDTHS = (512, 1024, 2048)
DEFAULT_ZSTD_LEVELS = (1, 3)
DEFAULT_REPETITIONS = 40
DEFAULT_WARMUPS = 4
PREVIEW_JPEG_QUALITY = 95

type Encoder = Callable[[], bytes]
console = Console()


@dataclass(frozen=True)
class FrameSample:
    catalog_index: int
    z_index: int
    width: int
    height: int
    source_bytes: int
    fetch_seconds: float
    minimum: int
    maximum: int
    mean: float


@dataclass(frozen=True)
class Result:
    catalog_index: int
    target_width: int
    width: int
    height: int
    source_bytes: int
    codec: str
    output_bytes: int
    compression_ratio: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_mpix_s: float


@dataclass(frozen=True)
class Settings:
    catalog_indexes: tuple[int, ...]
    target_widths: tuple[int, ...]
    zstd_levels: tuple[int, ...]
    jpeg_quality: int
    repetitions: int
    warmups: int
    stretch_low_percentile: float
    stretch_high_percentile: float


def _csv_ints(value: str) -> tuple[int, ...]:
    try:
        values = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from error
    if not values:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return values


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog-indexes",
        type=_csv_ints,
        default=DEFAULT_CATALOG_INDEXES,
        help="Comma-separated bench.data.CATALOG indexes (default: 0,1,2)",
    )
    parser.add_argument(
        "--widths",
        type=_csv_ints,
        default=DEFAULT_TARGET_WIDTHS,
        help="Comma-separated preview target widths (default: 512,1024,2048)",
    )
    parser.add_argument(
        "--zstd-levels",
        type=_csv_ints,
        default=DEFAULT_ZSTD_LEVELS,
        help="Comma-separated Zstandard levels; the first is also tested without shuffle (default: 1,3)",
    )
    parser.add_argument("--jpeg-quality", type=int, default=PREVIEW_JPEG_QUALITY)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--stretch-low-percentile", type=float, default=1.0)
    parser.add_argument("--stretch-high-percentile", type=float, default=99.9)
    parser.add_argument("--json-output", type=Path, help="Optionally write settings and aggregate results as JSON")
    return parser.parse_args()


def _settings(args: argparse.Namespace) -> Settings:
    if any(index < 0 or index >= len(CATALOG) for index in args.catalog_indexes):
        raise SystemExit(f"catalog indexes must be between 0 and {len(CATALOG) - 1}")
    if any(width <= 0 for width in args.widths):
        raise SystemExit("preview widths must be positive")
    if not 1 <= args.jpeg_quality <= 100:
        raise SystemExit("JPEG quality must be between 1 and 100")
    if args.repetitions <= 0 or args.warmups < 0:
        raise SystemExit("repetitions must be positive and warmups must be non-negative")
    if not 0 <= args.stretch_low_percentile < args.stretch_high_percentile <= 100:
        raise SystemExit("stretch percentiles must satisfy 0 <= low < high <= 100")
    return Settings(
        catalog_indexes=args.catalog_indexes,
        target_widths=args.widths,
        zstd_levels=args.zstd_levels,
        jpeg_quality=args.jpeg_quality,
        repetitions=args.repetitions,
        warmups=args.warmups,
        stretch_low_percentile=args.stretch_low_percentile,
        stretch_high_percentile=args.stretch_high_percentile,
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _measure(function: Encoder, *, pixels: int, repetitions: int, warmups: int) -> tuple[bytes, list[float]]:
    for _ in range(warmups):
        function()

    timings: list[float] = []
    output = b""
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            output = function()
            timings.append((time.perf_counter_ns() - started) / 1e6)
    finally:
        if gc_was_enabled:
            gc.enable()
    if not output or pixels <= 0:
        raise RuntimeError("encoder produced no output")
    return output, timings


def byte_shuffle(frame: np.ndarray) -> np.ndarray:
    """Return canonical low-byte plane followed by high-byte plane."""
    canonical = np.ascontiguousarray(frame.astype("<u2", copy=False))
    pairs = canonical.view(np.uint8).reshape(-1, 2)
    shuffled = np.empty(canonical.size * 2, dtype=np.uint8)
    shuffled[: canonical.size] = pairs[:, 0]
    shuffled[canonical.size :] = pairs[:, 1]
    return shuffled


def byte_unshuffle(shuffled: bytes, shape: tuple[int, int]) -> np.ndarray:
    """Reconstruct a little-endian uint16 image from canonical byte planes."""
    pixels = shape[0] * shape[1]
    planes = np.frombuffer(shuffled, dtype=np.uint8)
    if planes.size != pixels * 2:
        raise ValueError(f"expected {pixels * 2} shuffled bytes, received {planes.size}")
    interleaved = np.empty(pixels * 2, dtype=np.uint8)
    interleaved[0::2] = planes[:pixels]
    interleaved[1::2] = planes[pixels:]
    return interleaved.view("<u2").reshape(shape)


def _default_jpeg_pixels(frame: np.ndarray) -> np.ndarray:
    """Match PreviewGenerator's default no-level-adjustment uint16-to-uint8 conversion."""
    return cv2.convertScaleAbs(frame, alpha=255.0 / np.iinfo(frame.dtype).max)


def _encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    """Encode the JPEG comparison locally; JPEG is no longer a camera preview API."""
    success, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return encoded.tobytes()


def _stretched_jpeg_pixels(frame: np.ndarray, low_percentile: float, high_percentile: float) -> np.ndarray:
    """Create a display-useful JPEG control instead of a nearly black full-range conversion."""
    low = float(np.percentile(frame, low_percentile))
    high = float(np.percentile(frame, high_percentile))
    if high <= low:
        return np.zeros(frame.shape, dtype=np.uint8)
    scaled = np.clip(frame, low, high)
    return ((scaled - low) * (255.0 / (high - low))).astype(np.uint8)


def _add_result(
    results: list[Result],
    *,
    catalog_index: int,
    target_width: int,
    frame: np.ndarray,
    codec: str,
    encoder: Encoder,
    repetitions: int,
    warmups: int,
) -> bytes:
    output, timings = _measure(encoder, pixels=frame.size, repetitions=repetitions, warmups=warmups)
    p50 = statistics.median(timings)
    results.append(
        Result(
            catalog_index=catalog_index,
            target_width=target_width,
            width=frame.shape[1],
            height=frame.shape[0],
            source_bytes=frame.nbytes,
            codec=codec,
            output_bytes=len(output),
            compression_ratio=frame.nbytes / len(output),
            p50_ms=p50,
            p95_ms=_percentile(timings, 0.95),
            p99_ms=_percentile(timings, 0.99),
            throughput_mpix_s=frame.size / p50 / 1000.0,
        )
    )
    return output


def _benchmark_preview(
    preview: np.ndarray,
    *,
    catalog_index: int,
    target_width: int,
    settings: Settings,
    results: list[Result],
) -> None:
    shuffled = byte_shuffle(preview)
    default_u8 = _default_jpeg_pixels(preview)
    stretched_u8 = _stretched_jpeg_pixels(
        preview,
        settings.stretch_low_percentile,
        settings.stretch_high_percentile,
    )
    codecs = {level: Zstd(level=level) for level in settings.zstd_levels}
    primary_level = settings.zstd_levels[0]
    primary_codec = codecs[primary_level]

    output = _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec=f"shuffle+zstd-{primary_level} total",
        encoder=lambda: primary_codec.encode(byte_shuffle(preview)),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )
    restored = byte_unshuffle(primary_codec.decode(output), preview.shape)
    if not np.array_equal(restored, preview):
        raise AssertionError("shuffle + Zstandard round trip was not bit-exact")

    _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec="shuffle only",
        encoder=lambda: byte_shuffle(preview).tobytes(),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )
    for level, codec in codecs.items():
        _add_result(
            results,
            catalog_index=catalog_index,
            target_width=target_width,
            frame=preview,
            codec=f"zstd-{level} shuffled encode",
            encoder=lambda codec=codec: codec.encode(shuffled),
            repetitions=settings.repetitions,
            warmups=settings.warmups,
        )
    _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec=f"zstd-{primary_level} unshuffled encode",
        encoder=lambda: primary_codec.encode(preview),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )
    _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec=f"jpeg-q{settings.jpeg_quality} total default levels",
        encoder=lambda: _encode_jpeg(_default_jpeg_pixels(preview), settings.jpeg_quality),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )
    _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec=f"jpeg-q{settings.jpeg_quality} encode default levels",
        encoder=lambda: _encode_jpeg(default_u8, settings.jpeg_quality),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )
    _add_result(
        results,
        catalog_index=catalog_index,
        target_width=target_width,
        frame=preview,
        codec=f"jpeg-q{settings.jpeg_quality} encode stretched levels",
        encoder=lambda: _encode_jpeg(stretched_u8, settings.jpeg_quality),
        repetitions=settings.repetitions,
        warmups=settings.warmups,
    )


def _print_results(results: list[Result]) -> None:
    table = Table(title="Raw preview codec benchmark")
    table.add_column("sample", justify="right")
    table.add_column("target", justify="right")
    table.add_column("actual", justify="right")
    table.add_column("codec")
    table.add_column("p50 ms", justify="right")
    table.add_column("p95 ms", justify="right")
    table.add_column("p99 ms", justify="right")
    table.add_column("MB", justify="right")
    table.add_column("ratio", justify="right")
    for result in results:
        table.add_row(
            str(result.catalog_index),
            str(result.target_width),
            f"{result.width}x{result.height}",
            result.codec,
            f"{result.p50_ms:.3f}",
            f"{result.p95_ms:.3f}",
            f"{result.p99_ms:.3f}",
            f"{result.output_bytes / 1e6:.3f}",
            f"{result.compression_ratio:.2f}x",
        )
    console.print(table)


def _write_json(path: Path, settings: Settings, samples: list[FrameSample], results: list[Result]) -> None:
    document = {
        "environment": {
            "machine": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
        },
        "settings": asdict(settings),
        "samples": [asdict(sample) for sample in samples],
        "results": [asdict(result) for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    console.print(f"wrote [cyan]{path}[/]")


def main() -> None:
    args = _parse_args()
    settings = _settings(args)
    samples: list[FrameSample] = []
    results: list[Result] = []

    for catalog_index in settings.catalog_indexes:
        ref = CATALOG[catalog_index]
        reader = open_full_res(ref.link, v3=ref.v3, verbose=True)
        z_index = ref.z_start + ref.n // 2
        console.print(f"fetching catalog[{catalog_index}] z={z_index}")
        started = time.perf_counter()
        full = reader.read_3d(z0=z_index, n=1)[0]
        fetch_seconds = time.perf_counter() - started
        sample = FrameSample(
            catalog_index=catalog_index,
            z_index=z_index,
            width=full.shape[1],
            height=full.shape[0],
            source_bytes=full.nbytes,
            fetch_seconds=fetch_seconds,
            minimum=int(full.min()),
            maximum=int(full.max()),
            mean=float(full.mean()),
        )
        samples.append(sample)
        console.print(
            f"loaded {sample.width}x{sample.height} uint16 ({sample.source_bytes / 1e6:.1f} MB) in "
            f"{sample.fetch_seconds:.1f}s; min={sample.minimum} max={sample.maximum} mean={sample.mean:.3f}"
        )

        for target_width in settings.target_widths:
            preview = PreviewFrame.from_source(
                full,
                camera_id="benchmark",
                source_stream_id="benchmark",
                layer=PreviewLayer.OVERVIEW,
                frame_idx=0,
                viewport=PreviewViewport(),
                target_width=target_width,
                valid_bits=16,
            ).decode()
            _benchmark_preview(
                preview,
                catalog_index=catalog_index,
                target_width=target_width,
                settings=settings,
                results=results,
            )
            console.print(f"benchmarked target {target_width} (actual {preview.shape[1]}x{preview.shape[0]})")

        del full
        gc.collect()

    _print_results(results)
    if args.json_output is not None:
        _write_json(args.json_output, settings, samples, results)


if __name__ == "__main__":
    main()

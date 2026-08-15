# ome-zarr-writer

A high-performance streaming writer for OME-Zarr v3 / OME-NGFF v0.5 multiscale volumes, built for microscopy acquisition. Frames arrive one at a time; the writer batches them, generates the multiscale pyramid on the fly, and flushes sharded chunks to a local path or S3.

## Pipeline

Each frame passes through a fixed pipeline. Ingestion never blocks on I/O — downsampling and writing happen on background workers while the next batch fills.

```
add_frame(frame)                 # one z-slice at a time
    → ring buffer                # frames accumulate into a batch (batch_z slices)
        → pyramid                # batch downsampled to every level (numba, numpy fallback)
            → array backend      # sharded, compressed write per pyramid level
                → [staging]      # optional: local scratch → s5cmd upload to S3
```

`end_stack()` drains the final partial batch and closes its dataset while retaining the reusable ring. Final
`close()` also releases that ring.

## Installation

The package is part of the uv workspace. Backends and tooling are optional dependency groups, installed as needed:

| Group | Provides |
|-------|----------|
| `ts` | TensorStore backend (default; local + S3) |
| `zarrs` | Zarr + Rust-codec backend (local filesystem) |
| `s3` | S3 credential/transfer support (boto3) |
| `ng` | Neuroglancer viewer helpers |
| `fastapi` | HTTP server for the Neuroglancer viewer |

```bash
cd omezarr
uv sync --group ts              # default backend
uv sync --group ts --group s3   # writing to S3
```

## Usage

A minimal single-channel write to a local dataset:

```python
from ome_zarr_writer import Local, OMEZarrWriter, WriterConfig, ScaleLevel, UIVec3D, UVec3D

config = WriterConfig(
    volume_shape=UIVec3D(z=1000, y=2048, x=2048),
    voxel_size=UVec3D(z=1.0, y=0.5, x=0.5),
    max_level=ScaleLevel.L5,
)

writer = OMEZarrWriter(slots=6)
writer.begin_stack(config, Local(target="/path/to/experiment"))
for frame in camera.stream():  # each frame is a [y, x] ndarray
    writer.add_frame(frame)
writer.end_stack()
writer.close()
```

Writing to S3 uses a concrete storage value. `DirectS3` writes directly to the target; `StagedS3` writes shards
to a fast local disk and uploads them per batch. Credentials are resolved from the configured `S3Store` strategy
and the standard AWS chain:

```python
from cloudpathlib import S3Path
from ome_zarr_writer import S3Store, StagedS3

storage = StagedS3(
    target=S3Path("s3://my-bucket/experiment.ome.zarr"),
    scratch="/fast/scratch",
    store=S3Store(),
)
writer.begin_stack(config, storage)
```

## Configuration

`WriterConfig` is a frozen Pydantic model describing one dataset (a single stack and channel). The destination is
a separate `Storage` value passed to `begin_stack()`.

| Field | Default | Meaning |
|-------|---------|---------|
| `volume_shape` | required | Full `(z, y, x)` extent of the level-0 volume |
| `voxel_size` | required | Physical size per axis |
| `voxel_unit` | `MICROMETER` | Unit for `voxel_size` |
| `dtype` | `UINT16` | Pixel data type |
| `max_level` | `L7` | Deepest pyramid level (downscale factor `2^level`) |
| `compression` | `BLOSC_LZ4` | Chunk compression codec |
| `downscale_type` | `GAUSSIAN` | Pyramid reduction — `MEAN`, `GAUSSIAN`, `MIN`, `MAX` |
| `target_shard_gb` | `1.0` | Target shard size, used to derive shard geometry |

Ring-buffer depth (`slots`) and backend are `OMEZarrWriter` constructor options rather than config fields.

## Backends

The backend is selected with `ArrayWriter.Backend`, passed to the writer as `backend=`.

| Backend | Targets | Status |
|---------|---------|--------|
| `Backend.TS` | TensorStore — local filesystem and S3 | Default |
| `Backend.ZARRS` | zarr-python with the zarrs Rust codec pipeline — local filesystem only | Implemented |
| `Backend.AQZ` | Acquire-zarr | Unsupported |

Each batch is held in a shared-memory ring slot (`BatchSlot`) whose worker process both downsamples and writes it, so the compress+write never contends with the capture loop's GIL.

## Layout

| Path | Responsibility |
|------|----------------|
| [`writer.py`](src/ome_zarr_writer/writer.py) | `OMEZarrWriter`, `WriterConfig`, batch orchestration and staging |
| [`dataset.py`](src/ome_zarr_writer/dataset.py) | OME-NGFF / Zarr v3 metadata, `ScaleLevel`, `Compression`, `DownscaleType` |
| [`array/`](src/ome_zarr_writer/array/) | `ArrayWriter` base and the TensorStore / zarrs backends |
| [`slot.py`](src/ome_zarr_writer/slot.py) | `BatchSlot` ring slot — worker process downsamples + writes one batch |
| [`pyramid.py`](src/ome_zarr_writer/pyramid.py) | Downsampling kernels (numba JIT, numpy reference) |
| [`transfer.py`](src/ome_zarr_writer/transfer.py) | s5cmd wrapper for staged S3 upload |
| [`viewer/`](src/ome_zarr_writer/viewer/) | Read-side loader and Neuroglancer helpers |

## Examples and tests

Runnable examples live in [`examples/`](examples/): `basic_write.py` (local write with read-back verification), `s3_backend_example.py` (S3 auth variants and staging), and `ng_viewer_fastapi.py` / `ng_viewer_httpd.py` (Neuroglancer visualization). Metadata validation tests are in [`tests/metadata/`](tests/metadata/).

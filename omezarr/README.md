# ome-zarr-writer

High-performance streaming writer for OME-Zarr v3 with multi-scale pyramids.

## Features

- Streaming writes with ring buffer architecture
- Multi-scale pyramid generation (on-the-fly downsampling)
- Multiple backends: TensorStore, Zarr, Acquire-zarr
- S3 and local filesystem storage
- Neuroglancer integration for real-time visualization

## Installation

```bash
pip install -e .
```

## Usage

```python
from ome_zarr_writer import OMEZarrWriter, WriterConfig, ScaleLevel
from ome_zarr_writer.backends.ts import TensorStoreBackend

cfg = WriterConfig(
    name="my_data",
    volume_shape=(100, 512, 512),
    max_level=ScaleLevel.L3,
)

backend = TensorStoreBackend(cfg, "/path/to/output")
writer = OMEZarrWriter(backend=backend, slots=4)

# Stream frames
for frame in frames:
    writer.add_frame(frame)

writer.close()
```

## License

MIT

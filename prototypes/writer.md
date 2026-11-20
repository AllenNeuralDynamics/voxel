# Image writer

Researched on 2026-11-19 (as `streaming.md`), revised on 2026-11-20. How images reach storage, and what is left to
do there. How the acquisition drives the cameras is in `acquisition.md`.

## What the code does

- **The writer streams.** `new_frame` (`omezarr/src/ome_zarr_writer/writer.py`) takes 1 frame at a time and moves to
  the next slot of its ring by itself. When every slot is still being written, it blocks; it never drops.
- **Writer batches stay.** `batch_frames` is whole shards along axis 0 and a multiple of the pyramid factor; the 3D
  pyramid needs the whole block. This is the writer's own buffering.
- **The camera grabs in counted runs.** `begin_batch(n)` (`src/vxl/devices/camera/area.py`) waits for a free slot,
  arms the camera for `n` frames, and stops it after them. Frames that come between runs are lost. The acquisition's
  chunk loop is built around this (`acquisition.md`).
- **An image is opened with its `Transform`.** `AreaCameraHandle.image(storage, subpath, transform, settings)` opens
  it for a block and closes it after, also on an error.
- **Progress:** the camera's `progress` stream gives `WriterProgress` (`collected`, `flushed`, `total`). `flushed`
  feeds the record's `frames_written`.
- **Dropped frames:** the drivers report them (`StreamInfo.dropped_frames`); nothing reads them yet.

## When the writer is full

Agreed on 2026-11-20, not built. The writer owns the rule, so the caller never checks for free slots:

```python
open_image(target, size, dtype, transform, settings, ram_bytes, when_full: Literal["wait", "drop"])

with writer.new_frame() as frame:   # unchanged: called for every frame
    device.grab_frame(out=frame)

writer.dropped -> list[FrameRange]  # what it dropped so far
```

- `"wait"`: `new_frame` blocks until a slot is free, as today. Step scans use it.
- `"drop"`: at a batch border with no free slot, the writer drops that whole batch by itself. For each frame of it,
  `new_frame` gives a scratch buffer and throws it away, so the camera's own buffer does not overflow. At the next
  border it tries again. Sweeps use it.
- Whole batches only: a batch is whole shards and a multiple of the pyramid factor, so a missing batch is just
  missing shards, read as the fill value at every level.
- `progress` (`WriterProgress`) gets a `dropped` count, and `metrics.json` notes dropped batches. `close()` works when
  the last batch was dropped.
- Where: `DatasetWriter` (`omezarr/`), the `ImageWriter` interface (`vxlib/src/vxlib/imaging/writer.py`), and the
  camera, which passes `when_full` through `open_image` and `image(...)` and reports `dropped`. `begin_batch` does not
  change.

## Geometry: OME-Zarr 0.6

Built. Sources: the specs index https://ngff.openmicroscopy.org/specifications/ and RFC-5
https://ngff.openmicroscopy.org/rfc/5/.

- The writer writes 0.6 metadata (`Zarr3GroupMeta.multiscale` in `omezarr/src/ome_zarr_writer/dataset.py`).
- 2 coordinate systems: `image` (the array's own axes, in physical units) and `specimen`.
- Each level has a `scale` into `image`; a coarser level is shifted so its pixel centers sit right.
- `image` goes to `specimen` by a translation when the steps run along +z, +y, +x, and by an `affine` otherwise. It
  comes from the image's `Transform`.
- A reader that skips the affine still gets a correct grid in physical units. Readers MUST read scale, translation
  and sequences; they only SHOULD read affine.

## Line scan (later)

A strip of lines can be 1 "frame", but strips stack along the line axis, not a new axis. The writer would need a strip
mode: 2D, appending along y, with a 2D pyramid. That is a real writer change, after the day-1 area cameras work.

## Open

- The array's dimension names are still `z, y, x` (`writer.py`, `_ARRAY_AXES` in `dataset.py`), with long names
  `frame, row, column`. Axis 0 is the scan, which is not always z. Name it truthfully, for example `scan`.
- Which viewers read 0.6 affines today: Neuroglancer does (checked by the user, 2026-11-20). napari and BigStitcher
  are not checked.
- A planner warning when a sweep's frame rate is above the rig's measured write rate.

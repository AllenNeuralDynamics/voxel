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

Agreed and built on 2026-11-20. The writer owns the rule, so the caller never checks for free slots:

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

## Pyramid depth and shards

Built on 2026-11-20 in `omezarr/src/ome_zarr_writer/writer.py`.

- **A batch is always whole shards.** The L0 chunk is `2^max_level` frames deep (width and height stay floored at
  `MIN_CHUNK_EDGE`, 64 px). Before, the depth was floored at 64 too, so a pyramid of 5 levels or fewer had batches
  smaller than a shard, and 2 slot workers could rewrite the same shard file at once; TensorStore's file store says
  such partial writes "may" lose updates (https://google.github.io/tensorstore/kvstore/file/index.html). exaSPIM
  (`max_level: 3`, 14192 x 10640 px frames) was in that case: its chunks are now 8 frames deep, and its batches stay
  8 frames (about 2.4 GB per slot).
- **A small frame gets fewer levels**, with a warning: the last level keeps at least `MIN_LEVEL_EDGE_PX` (16) pixels
  on the shorter side, and always at least 1 pixel whatever the constant says (`_levels_that_fit`). A full 2048 px
  sensor with 7 levels and a full exaSPIM frame with 3 are unchanged.
- Fewer levels mean shallower shards; the batch stays close to `batch_frames`, rounded up to whole shards.

## Batch size in frames

Built on 2026-11-20. `WriterSettings.batch_frames` (128 by default) gives the frames in 1 batch; the writer rounds it
up to whole shards (`rounded_batch_frames`), so it sets the stops of a step scan and the memory of a slot directly,
whatever the pyramid depth. It replaced `batch_shards` everywhere: the SPIM `WriterFields`, the legacy `WriterPatch`
and the legacy web app (rebuilt), and the saved legacy `state.json` files (now in `~/.voxel/legacy/instruments/`), each given the batch it had
before. The exaSPIM template sets `batch_frames: 8`.

A camera reports its open image's real batch (`AreaCameraHandle.batch_frames()`): a small frame can get fewer levels,
so smaller shards. A step scan arms the cameras for the smallest of their batches, so each of its batches waits for a
free buffer on every camera.

## Memory per camera (not built)

Each camera's computer has a budget: free RAM x `max_ram_fraction` (0.75 by default, `System.ram_budget_bytes`),
split between its cameras (`RamBudget`). The writer fits 2 to 4 slots in it (`MIN_SLOTS`, `MAX_SLOTS` in
`sizing.py`); a slot costs a batch plus its pyramid and the worker's buffers (`per_slot_bytes`). If 2 do not fit, the
image fails to open with `RingSizingError`, today at the first visit.

Seen on 2026-11-21, on a laptop with a budget of 14.9 GB: the simulated `z-step.yaml` template with its own writer
settings (`batch_frames: 128`, `max_level: 3`) needs 60 GB for 1 slot. `start_acquisition` answered with an id, the
record was made, and the visit then failed with "cannot fit 2 batch slots". With `batch_frames: 2` and
`max_level: 1` the same acquisition completed.

- **Camera query:** for an image (its transform) and the writer settings, give the memory per slot, the camera's
  budget and how many slots fit. It reuses `per_slot_bytes` and `slots_for_budget`, and runs on the camera's computer
  where the budget is.
- **Start check:** `start_acquisition` asks it for every image of the plan and refuses before the record exists
  when fewer than 2 slots fit.
- **UI:** the writer section shows the batch in frames and, for each camera of the active profile, its frame size,
  memory per slot, budget and slots that fit, with a warning under 2. More slots give a sweep more slack before it
  drops a batch.

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

# Streaming capture

Researched on 2026-11-19, not built. Why: the refactor is for new geometries and scan methods (exaSPIM sweep,
open-top light sheet, SeqSweep TDI line scan), and the camera and acquisition code assume stepped Z stacks in
batches. See `acquisition.md` and `records.md`.

## What the code does today

- **The writer already streams.** `DatasetWriter.new_frame` (`omezarr/src/ome_zarr_writer/writer.py:437`) takes 1
  frame at a time and cuts batches itself (`frames_added // batch_z`). When it falls behind, it blocks; it never drops.
- **The camera controller does not.** `begin_batch(n)` (`src/vxl/devices/camera/area.py:391`) waits for a free slot,
  arms the camera for `n` frames, and `_collect_batch` (`:423`) stops the camera after them. Frames that arrive
  between batches are lost, so a sweep cannot run.
- **The old loop** (`src/vxl/_legacy/instrument/core.py:1630`) starts and stops the triggers around each batch.
- **Dropped frames are not checked.** The drivers report them (`dropped_frames` in egrabber, ximea, pco), and nothing
  reads them.
- **Geometry in the file:** axes `c, z, y, x` and a scale from `z_step` and the magnification. No translation.
  `open_stack(num_frames, z_step, magnification)` names the scan axis "z".
- **Line camera:** `src/vxl/devices/camera/line.py` is a stub.

## Batches: needed, but inside the writer

- `batch_z` is whole shards along the stack axis and a multiple of the pyramid factor (`writer.py:97`). The 3D
  pyramid needs the whole block. These stay, as the writer's own buffering.
- Arming per batch, `ready_for_batch`, and stopping the triggers between batches are control flow only. They go.

## The design

- **The camera controller needs no new action.** `begin_batch(n)` has no limit tied to `batch_z`: it arms the camera
  for `n` frames and grabs them into the writer, which moves to the next slot itself.
- **Steps keep today's way.** Between batches the loop stops the triggers and waits for a free slot. That is flow
  control: the writer can never fall behind, so a stack can be any size.
- **Sweeps get 1 `begin_batch` for the whole visit.** The stage cannot wait, so there is no flow control. When every
  slot is busy, `_assign_collecting_slot` (`writer.py`) blocks, the grab task stops reading, frames pile up in the
  driver's buffer (about 4 GB on egrabber), and then drop.
  - The slack is about `(slots - 1) * batch_z` frames plus the driver buffer. The slot count comes from the RAM budget.
  - If the workers keep up on average, a sweep can be any length. If not, the slack runs out after about
    `slack / (camera rate - write rate)` seconds, so a long sweep on a slow writer must be split into several visits.
- **Progress:** from the camera (`writer_metrics`; not yet checked what it holds) as `frames_written`.
- **Failure:** a visit fails on dropped frames (`dropped_frames`, checked at the visit end), a grab timeout, or a
  writer failure.
- **The loop:** arm the cameras, arm the stage (`arm_steps` or `sweep`), load the generators with the trigger chain's
  starts (`InputEdges` for those that wait), start the starters, follow progress, stop.

## Geometry: OME-Zarr 0.6

Sources: the specs index https://ngff.openmicroscopy.org/specifications/ and RFC-5
https://ngff.openmicroscopy.org/rfc/5/.

- 0.4 and 0.5 allow only `scale` and `translation` per dataset. Space axes SHOULD be `z, y, x`; names only need to be
  unique.
- 0.6 is released (2026-09-14, per the RFC-5 changelog) and includes RFC-5: named coordinate systems and `affine`,
  `rotation`, `sequence` and more. Readers MUST read scale, translation and sequences; they only SHOULD read affine.
- Plan (my judgment, from the research):
  - Name the array axes truthfully, for example `scan, y, x`; never call a scan axis `z`.
  - Each level: a `scale` (+ translation) into the array's own coordinate system.
  - At the multiscale level: an `affine` from that system to a named `stage` coordinate system. It comes straight from
    the image's `Transform` (`Transform.matrix`).
  - A reader that skips the affine still gets a correct grid in physical units.
- `open_stack` takes the image's `Transform` in place of `z_step` and the magnification.
- Not checked: which viewers (napari, BigStitcher, Neuroglancer) read 0.6 affines today.

## Line scan (later)

A strip of lines can be 1 "frame", but strips stack along the line axis, not a new axis. The writer would need a strip
mode: 2D, appending along y, with a 2D pyramid. That is a real writer change, after the day-1 area cameras work.

## Open

- Writer target: move from 0.5 to 0.6 metadata.
- What `writer_metrics` holds, and whether it gives `frames_written`.
- A planner warning when a sweep's frame rate is above the rig's measured write rate.
- Records: design A (snapshots, with context managers) or B (event log), in `prototypes/records/`. Both store
  `frames_written` per image.

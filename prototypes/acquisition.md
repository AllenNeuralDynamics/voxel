# Acquisition

Discussed on 2026-11-18, written down on 2026-11-19, revised on 2026-11-20. Not built. The records it writes are
built in `src/vxl/records/` (see `records.md`).

## Where it lives

- All of it is SPIM's: `instruments/src/vxl_instruments/spim/`, in the `Microscope` class, next to the preview.
- The base `Instrument` gets no acquisition hooks. It only keeps `self._records`, which the station gives every kind.
- Rule: the base holds data every kind has in the same shape (tasks, metadata, undo, the records handle). A kind
  holds what drives devices (preview, acquisition). When a 2nd kind acquires, the shared part moves into the base.
- It runs as the activity `acquisition`, started with `stop=`, so `Instrument.stop()` and `close()` end it through
  `ActivityScheduler.stop_all()`.

## Commands

```python
async def start_acquisition(self, storage: StorageSpec, operator: str) -> UUID:
    """Start acquiring the plan in the background, and give back the new acquisition's id."""

async def stop_acquisition(self) -> None:
    """Cancel the running acquisition and wait for its cleanup."""
```

- `storage` and `operator` are asked each time: a lab computer often has 1 shared login, and each acquisition goes
  to a folder or remote store that the operator picks.
- `host` comes from `System.hostname()`.
- The whole plan runs. A list of `task_ids` (as in the legacy loop) is left out; it can come later as 1 optional
  argument.
- The run is a background task. `start_acquisition` returns once the record exists.

## Live state

```python
class AcquisitionInfo(ActivityInfo):
    kind: str = "acquisition"
    acquisition_id: UUID
    visit: int          # the index of the visit that runs now
    visits: int         # how many visits in total
    phase: Phase        # planning | visiting | ending
```

- The loop calls `activity.update(...)`; `view.activities` carries it. `InstrumentView` gets no acquisition fields.
- Frame counts are in the record (`frames_written` per image), not on the activity.
- Time left is measured, not planned: frames still to write ÷ the frame rate so far. There is no estimate before
  Start.
- The record reaches screens through `AcquisitionStore.subscribe`, the log through `LogJournal.subscribe` (see
  `feed.md`).

## Frozen at Start

- The plan becomes SPIM's `Volume`s (`plan_task` in `spim/plan.py`), kept in memory for the whole acquisition.
  Nothing patches them while it runs.
- The loop reads the `Volume`s, never the record. The record only describes what happened.
- The config and state, with each task's metadata, are frozen into the record (`instrument_config`,
  `instrument_state`).

## The flow

1. Stop the preview. Check that each camera of the plan can write `storage` (`check_writable`), before anything is
   recorded.
2. Freeze the plan into `Volume`s. Build the `Acquisition`, with 1 `Visit` per `Volume` and 1 `Image` per camera
   (from `Volume.transforms`).
3. `async with records.record(acquisition) as run:` for each visit, `async with run.visit(i) as visit:`
   - lights off, apply the profile, move the stage to the visit's start,
   - open 1 image per camera with `async with camera.image(...)` (an `AsyncExitStack` for several cameras), then
     `visit.images_opened(locations)`,
   - reset the live streams, as `_begin_preview` does,
   - run the chunk loop (below), reporting `visit.frames(camera, written)`,
   - in a `finally` inside the image blocks: lights off, generators stopped, the axis halted. The images close after.
4. After the last visit, or on a stop or an error: release each camera's writer.

`Records.record` and `Recording.visit` already set every status: a normal end completes, a cancel cancels, an error
fails, missing frames fail the visit, and visits that never started are skipped. The loop never names a status.

## The chunk loop

A visit runs in chunks. Between chunks, the loop waits until every camera has a free writer slot. That is the brake:
a slow disk makes the scan wait instead of losing frames. A chunk is at most what fits in the free slots.

| Motion | Pacer | 1 chunk |
| --- | --- | --- |
| step | a device | `begin_batch(n)` on each camera, `arm_steps` for `n` steps, start the generators for `n` cycles |
| step | `software` | for each frame: move the axis, then play 1 cycle |
| sweep | a device | a **segmented sweep**: 1 short sweep of `n` frames |

**Segmented sweep:** 1 visit and 1 image, but the stage runs the strip as several shorter sweeps.

- The image opens 1 time, for all frames.
- For each segment: arm the cameras (`begin_batch(n)`), load each generator with `InputEdges(pin)`, start it for `n`
  cycles, then `sweep(Sweep(first, last, speed, Pulses(n, pin)))`. Each stage pulse plays 1 cycle, and each cycle
  triggers 1 frame.
- Segment `k` starts its first pulse at frame `k`'s position. Each segment adds 1 run-up.
- If the whole strip fits in the free slots, there is 1 segment: the same as 1 long sweep.
- The generator's pin is the wire from `SPIMProfile.trigger_chain(config).waits`.
- The loop uses the spacing that `sweep()` gives back (the sweep the axis really runs), not the planned one.

Why chunks: the writer (`omezarr/src/ome_zarr_writer/writer.py`) already moves to the next slot by itself and blocks
when all are busy. But the camera's `begin_batch(n)` stops after `n` frames, and a sweeping stage cannot wait for it.

## Resources

The `acquisition` activity holds, with no restart:

- the store: every edit is refused during a run (plan, profiles, powers, properties, tuning knobs), as the legacy
  "busy" state did. The run reads its frozen copy, so plan edits could later be allowed with a finer resource.
- the devices of every profile in the plan: cameras, generators, lights and the devices on their paths, and the stage.
- `_power_mode`: `set_power_mode` holds nothing today (`requires=()`), so it would switch every light between full and
  dim during a run. It must hold `_power_mode`. The preview does not hold it, so the preview still changes at once.

Left as they are, on purpose:

- A power edit holds only the store, not the light. Holding the light would restart the preview on every slider move.
  The store already refuses it during a run.
- `lights_off` and `lasers_off` are failsafes and hold nothing: they always work, also during a run.

## Stopping

- `stop_acquisition` and `stop_all()` cancel the run's task and wait for its cleanup.
- A camera grab that waits for a trigger blocks a stop on the same device thread. The stop must end that grab.

## Device calls

- Camera handle: `check_writable`, `image(...)` (wraps `open_image` and `close_image`), `begin_batch`,
  `capture_state`, `release_writer`, `reset_live_stream`.
- Axis handle: `move_to`, `arm_steps`, `sweep`, `halt`, `run_up`, `scan_state`.
- Generator handle: `load`, `start(count)`, `stop`, `wait_until_done`.
- Hal: `lights_on`, `lights_off`.

## Stage drivers

- Only `SimulatedLinearAxis` has `sweep` and `arm_steps` today. ASI Tiger (`drivers/src/vxl_drivers/axes/asi.py`),
  MMC and Thorlabs still use the legacy axis with a TTL stepper only.
- ASI hardware can run a segmented sweep: `SCANR` takes a start and a stop, the pulse output goes high as the stage
  crosses the start, then 1 pulse every N encoder counts; the stage overshoots both ends so the speed is steady
  between them. Sources: https://asiimaging.com/docs/commands/scanr and https://asiimaging.com/docs/scan_module.
- So a first pulse lands on the start to 1 encoder count, and the spacing is a whole number of counts.

## To do

- `start_acquisition`, `stop_acquisition` and `AcquisitionInfo` on `Microscope`.
- The flow and the chunk loop for the 3 rows of the table.
- The resources above, and `set_power_mode` holding `_power_mode`.
- Ending a waiting camera grab on a stop.
- Reading the drivers' dropped frames (`StreamInfo.dropped_frames`); nothing reads them today.
- `Records.record` writes `acquisition.log.jsonl` at the end (`AcquisitionStore.write_log` exists, nothing calls it).
- A new ASI Tiger axis driver with `sweep` and `arm_steps`, outside `instruments/`; ask before starting it.

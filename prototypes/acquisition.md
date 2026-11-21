# Acquisition

Discussed on 2026-11-18, written down on 2026-11-19, revised on 2026-11-20 after 2 code reviews. **Built** on
2026-11-20 in `Microscope` (`spim/instrument.py`): the 3 scans as `_step_scan`, `_software_scan` and `_sweep_scan`,
tested on simulated devices that pass their edges along the wires (`instruments/tests/spim/test_acquisition.py`). The
records it writes are built in `src/vxl/records/` (see `records.md`); the writer side is in `writer.md`.

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
- `stop_acquisition` is a failsafe: it never goes through the scheduler (see "The scheduler").

## Live state

```python
class AcquisitionInfo(ActivityInfo):
    kind: str = "acquisition"
    acquisition_id: UUID
    visit: int          # the index of the visit that runs now
    visits: int         # how many visits in total
    stopping: bool      # a stop was asked for, or the run is ending
```

- The loop calls `activity.update(...)`; `view.activities` carries it. `InstrumentView` gets no acquisition fields.
- A stop request sets `stopping` at once, as the legacy loop set `STOPPING` (`_legacy/instrument/core.py:771-774`).
- Frame counts are in the record (`frames_written` and `dropped` per image), not on the activity.
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
- `_apply_profile` reads the profile from the store, not from a frozen copy (`base.py:494`). That is sound only
  because the run holds the store. If plan edits are ever allowed during a run, apply from a snapshot.

## The scheduler

- **The run never calls `scheduler.run`.** The run's activity holds every device with no restart, so any operation
  that names one is refused by the run itself (`activity.py:154`). And `close()` holds the scheduler lock while
  `stop_all()` waits for the run's cleanup (`base.py:204`), so a cleanup that took the lock would deadlock. The loop
  calls `_apply_profile`, `_move_axis` and the device handles directly.
- **The task starts with a fresh context** (`asyncio.create_task(..., context=contextvars.Context())`). A task made
  inside `start_acquisition`'s operation would copy its "inside an operation" mark and skip the lock
  (`activity.py:94`). The "record exists" signal comes back through a future that also carries a startup error.
- **Task housekeeping:** the instrument keeps a reference to the task; the task logs its own error (the records raise
  it again, `records.py:191-193`) instead of leaving "Task exception was never retrieved"; on a normal end it calls
  `activity.end()` itself.

## Resources

The `acquisition` activity holds, with no restart:

- every device of the instrument, to be safe;
- the store: every edit is refused during a run (plan, profiles, powers, properties, tuning knobs), as the legacy
  "busy" state did;
- `_active_profile`;
- `_power_mode`: `set_power_mode` holds nothing today (`requires=()`), so it would switch every light between full and
  dim during a run. It must hold `_power_mode`. The preview does not hold it, so the preview still changes at once.

Changes outside the run:

- `execute_device_command` refuses an action on a device that the run holds. Today it holds nothing and its docstring
  says "None of them restarts or refuses an activity" (`base.py:259-266`). Queries and failsafes still run at once.

Left as they are, on purpose:

- A power edit holds only the store, not the light. Holding the light would restart the preview on every slider move.
  The store already refuses it during a run.
- `lights_off` and `lasers_off` are failsafes: they always work, also during a run.

## The flow

1. Stop the preview. Check that each camera of the plan can write `storage` (`check_writable`), before anything is
   recorded.
2. Freeze the plan into `Volume`s. Build the `Acquisition`, with 1 `Visit` per `Volume` and 1 `Image` per camera
   (from `Volume.transforms`). Set the power mode to `full` for the whole run; it is not set back after.
3. `async with records.record(acquisition) as run:` for each visit, `async with run.visit(i) as visit:`
   1. Apply the profile with `_apply_profile` (it turns every light off first).
   2. Move the stage to the visit's start, wait until it is still, then set `Volume.positions`. `_apply_profile` set
      the stage-following devices for where the stage was before the move (`base.py:507`); the planner already
      worked out the right ones for this stop.
   3. Open 1 image per camera, at `<visit>/<profile>/<channel>/<camera>` under the storage, with
      `async with camera.image(..., when_full=...)` (an `AsyncExitStack` for several
      cameras), then `visit.images_opened(locations)`.
   4. Reset the live streams after `_apply_profile`, as `_begin_preview` does.
   5. Run the batch loop (below). Turn the lights on with `hal.lights_on(sources)` after the cameras are armed for
      the first batch and before the generators start, as the legacy loop did (`core.py:1653-1655`). A laser whose
      light has no path to the sample fails the visit (the preview only warns).
   6. Each camera's `progress` stream is subscribed while its image is open; each change goes to
      `visit.frames(camera, collected)`, which the records save at most once a second. Report
      `visit.frames_dropped(camera, ranges)` before the visit ends.
   7. Clean up in a `finally` inside the image blocks, so the images close after: lights off, generators stopped,
      the axis halted. Every step runs even when one fails, and the errors are raised together; reuse the step
      runner of `_stop_preview_devices`. A cleanup error never hides the error that ended the visit.
4. After the last visit, or on a stop or an error: release every camera's writer. 1 failure does not stop the others,
   and failures are only logged: the record has already ended.
5. The active profile stays as the last visit's profile.

`Records.record` and `Recording.visit` already set every status: a normal end completes, a cancel cancels, an error
fails, missing frames fail the visit, and visits that never started are skipped. The loop never names a status.

## Scan direction

With `path.scan: {<axis>: alternate}` on the task, every 2nd stop along the tile path runs from the far end back
(`plan_task`): its `AxisRun` starts at the last frame position with a negative spacing, over the same frame
positions, so the stage never travels back across the region. All profiles at 1 stop run the same way. A step scan
arms negative steps, a sweep runs `last < first`, and the image's transform gets a reversed axis, so every pixel
still lands at its specimen position.

## The batch loop

A visit runs in batches of the writer's `batch_frames`. The writer's ring holds several batches in memory while
workers write them to disk.

| Motion | Pacer | How a visit runs | When the writer is full |
| --- | --- | --- | --- |
| step | a device | per batch: `begin_batch(n)` on each camera, `arm_steps` for `n` steps, `start(n)` on each generator, wait until every camera is `DONE`, `wait_until_done` on the generators | `when_full="wait"`: `begin_batch` waits for a slot, and the stage waits with it. No frame is lost. |
| step | `software` | per frame: `move_to(p, wait=True)`, then `start(1)` and `wait_until_done` on each generator; the cameras are armed per batch and the axis is never armed | `"wait"`, as above |
| sweep | a device | 1 `begin_batch(all frames)` on each camera, each generator loaded with `InputEdges(pin)` and started for all frames, then 1 `sweep(Sweep(first, last, speed, Pulses(count, pin)))` | `when_full="drop"`: the writer drops each whole batch that finds no free slot, and the sweep goes on. The record reports the dropped frames. |

- The user must not run a sweep faster than the writer can keep up; dropped batches are reported, not prevented.
- A generator's 2nd `start(n)` does nothing while its state is still `running` (`generator/base.py:108`). Each batch
  ends with `wait_until_done` (it also stops) before the next `start`.
- `begin_batch` raises while the last batch still runs (`area.py:353`), so the loop waits for `DONE` on every camera
  first. `capture_state` raises once a batch has failed, which ends the visit.
- Step: `arm_steps` checks travel from the current position, so steps go on from where the last batch stopped. It
  follows `move_to(start, wait=True)`.
- Sweep: the generator's pin is the wire from `SPIMProfile.trigger_chain(config).waits`. The loop uses the sweep that
  `sweep()` gives back (what the axis really runs), not the planned one. A sweep needs at least 2 frames
  (`Pulses.count >= 2`); a 1-frame visit runs as a step.
- Sweep: `margin` must be above 0. With 0, a pulse comes exactly 1 cycle after the last (`plan.py:121`), and a
  generator ignores a pulse while a cycle plays (the simulated one does too, `generator/simulated.py:156-158`), so 1
  late pulse loses a frame.
- Load is free when the cycle is the same (`generator/base.py:79-80`), so the loop can load once per visit.

## Stopping

Picked on 2026-11-20: no new camera action.

- A stop cancels the run's task. The cleanup stops the generators, so no more triggers come. Each camera grab that
  waits gives up after its timeout, the batch fails, and the image can close. Today `close_image` and
  `release_writer` raise while a batch still runs (`area.py:273`, `317`).
- So a stop takes up to 1 grab timeout. Every real camera driver needs a grab timeout longer than its slowest frame;
  the simulated camera has one (`trigger_timeout_s`).
- `Instrument.stop()` promises to never wait for the running command (`base.py:221`). The run's `stop` therefore waits
  for its cleanup with a time limit, and `hal.stop()` runs even when that limit passes.
- Later, if stops feel slow: an `abort_batch()` camera action that stops the driver from a 2nd thread.

## Device calls

- Camera handle: `check_writable`, `image(..., when_full)` (wraps `open_image` and `close_image`), `begin_batch`,
  `capture_state`, `release_writer`, `reset_live_stream`, `ready_for_batch`; new: `progress`, `dropped`,
  `wait_for_batch(batch)`, `wait_until_collected`. The waits follow the camera's `capture` stream
  (`CaptureStatus`: `batch`, `state`, `error`); `begin_batch` and `close_image` give back the number to wait for, so a
  stale value from an earlier batch never ends a wait. The `capture_state` query stays for the legacy loop.
- Axis handle: `move_to`, `wait_until_still`, `arm_steps`, `sweep`, `halt`, `run_up`, `scan_state`.
- Generator handle: `load`, `start(count)`, `stop`, `wait_until_done`.
- Hal: `lights_on`, `lights_off`.

## Stage drivers

- Only `SimulatedLinearAxis` has `sweep` and `arm_steps` today. ASI Tiger (`drivers/src/vxl_drivers/axes/asi.py`),
  MMC and Thorlabs still use the legacy axis with a TTL stepper only.
- ASI hardware can sweep with pulses: `SCANR` takes a start and a stop, the pulse output goes high as the stage
  crosses the start, then 1 pulse every N encoder counts; the stage overshoots both ends so the speed is steady
  between them. Sources: https://asiimaging.com/docs/commands/scanr and https://asiimaging.com/docs/scan_module.
- So a first pulse lands on the start to 1 encoder count, and the spacing is a whole number of counts.

## Dropped: segmented sweeps

Proposed and dropped on 2026-11-20, on advice. A sweep split into short sweeps, waiting for free slots between them,
would lose no frames but adds a run-up and a turn-around per segment. Instead, a sweep is 1 sweep, and frames that
the writer cannot take are dropped by whole batches and reported.

## To do

- Reading the drivers' dropped frames: see `src/vxl/devices/camera/dropped-frames.md`.
- Memory per camera, checked at Start: see `writer.md`.
- A new ASI Tiger axis driver with `sweep` and `arm_steps`, outside `instruments/`; ask before starting it.

## Simulation notes

- Simulated devices that send edges from their own helper threads hand each one to the wiring's thread with
  `Device.call_soon`; rigup refuses a call into a device from a thread that is not a device's.
- A simulated sweep needs a wide margin (the test uses 30 %): Python threads can be several ms late, and a generator
  misses a pulse while it plays a cycle.

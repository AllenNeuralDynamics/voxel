# Acquisition

Discussed on 2026-11-18, written down on 2026-11-19, not built. Planned together with the records:
see `records.md`.

## Where it lives

- The acquisition loop is SPIM's: `src/vxl/instruments/spim/`, in the `Microscope` class. It runs as the
  activity `acquisition`, started by `start_acquisition` and stopped by `stop_acquisition`, the same way a preview runs.
- **Base:** record keeping, progress, and the cleanup after an error.
- **SPIM:** turning tasks into `Volume`s (`plan_task` in `spim/plan.py`), and running 1 `Volume`.

## Frozen at Start

- At Start, the plan becomes SPIM's `Volume`s, kept in memory for the whole acquisition. They are frozen (`FrozenMap`, frozen
  models). Nothing patches them while the acquisition goes on.
- The acquisition reads the `Volume`s. It never reads the record. The record only describes what happened.
- Task metadata is frozen at Start too, in `instrument_state`.

## The loop

Copied from the old loop in `src/vxl/instrument/core.py` (`start_acquisition` and its loop, lines 673 and 1505–1720):

1. Stop the preview. Check that each camera can write to the storage.
2. Create the record: the `Acquisition`, and each visit and image as `pending`. Open the log window.
3. For each `Volume`: apply the profile, move the stage, open a stack on each camera, save the image locations, then
   capture in batches. Report `done` after each batch.
4. Cleanup for each `Volume`: lights off, generators stopped, stacks closed. Then set the visit and image status.
5. At the end: unrun visits become `skipped`. Set the acquisition status, release the writers, close the log window
   and write `acquisition.log.jsonl`.

## What changes from the old loop

- It uses the new `Volume` and `AxisRun`.
- It moves the stage with `arm_steps` or `sweep`, as `Scan.motion` says. The old loop used `queue_relative_move`.
- It turns on lights with `hal.lights_on`. The old loop used channel objects.
- It resets the live streams after the cameras start, the same way `_begin_preview` does.

## Hooks

Agreed on 2026-11-19.

| Name | Who | What |
| --- | --- | --- |
| `_plan_visits(state)` | SPIM fills in | At Start: turns tasks into frozen `Volume`s, returns 1 `VisitPlan` per `Volume` |
| `_run_visit(index)` | SPIM fills in | Applies the profile, moves the stage, opens the stacks, captures in batches |
| `_end_visit(index)` | SPIM fills in | After each visit, also after a failure: lights off, generators stopped, stacks closed |
| `_report_progress(done)` | base gives | SPIM calls it after each batch; the base writes it at a capped rate |
| `_register_images(index, locations)` | base gives | SPIM calls it after the stacks open; the base writes it to the record |

`VisitPlan`: `task`, `profile`, `images` (channel and camera), `total`, `unit`, `expected_s`.

## Live state

Agreed on 2026-11-19.

- **Progress is on the activity.** `AcquisitionInfo(ActivityInfo)` holds the acquisition `id`, the visit that runs,
  the number of visits and its `Progress`. The loop calls `activity.update(...)` on each report, and `view.activities`
  already carries it. `InstrumentView` gets no acquisition fields.
- **The record comes from the records.** `AcquisitionStore.subscribe` gives each stored revision; the feed sends it as
  a records topic. The instrument view never holds a copy.
- **Logs come from the records too.** `LogJournal.subscribe` gives each line; the feed sends it as an append topic, with
  `seq` as the cursor.
- A screen shows the record and lays the activity's live count over the running visit. The activity's `id` links them.

```text
instrument ──view (activities + progress)──┐
records ──log lines (append)───────────────┼──▶ feed ──▶ proxy ──▶ screens and lab
records ──acquisition revisions────────────┘
```

## Logs before, during and after

- The journal starts with `vxl station start`, not with the web app, and catches every log line of the session.
- At Start, after the record exists, the loop opens the acquisition's window (`log_start_seq`); at the end it closes
  it (`log_end_seq`). The window holds every station line in that time, node lines too (`node_id`).
- After the end, the loop reads the window in pages (at most 10,000 lines per read) and writes
  `acquisition.log.jsonl` 1 time.
- Open: how long the `logs` table keeps lines outside any window.

## Device calls already there

- Camera: `open_stack`, `begin_batch`, `capture_state`, `close_stack`, `release_writer`, `check_writable`.
- Stage: `move_to`, `arm_steps` (step scans), `sweep` (sweep scans).
- Generators: `start`, `stop`, `wait_until_done`.

## Open

- Whether the base needs a hook so that `_end_activities` also stops an acquisition. Not confirmed.
